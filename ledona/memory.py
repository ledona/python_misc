"""
Available/total memory code that accounts for container boundaries if run in a container.
originally implemented with Gemini
"""

import os
import sys
from enum import Enum
from logging import log
from typing import Callable, Literal, get_args

import psutil


def get_total_memory():
    """Returns the effective memory limit in bytes, respectng container bounds."""
    # 1. Check Cgroup v2
    cgroup_v2_path = "/sys/fs/cgroup/memory.max"
    if os.path.exists(cgroup_v2_path):
        with open(cgroup_v2_path, "r") as f:
            val = f.read().strip()
            if val != "max":
                return int(val)

    # 2. Check Cgroup v1
    cgroup_v1_path = "/sys/fs/cgroup/memory/memory.limit_in_bytes"
    if os.path.exists(cgroup_v1_path):
        with open(cgroup_v1_path, "r") as f:
            val = int(f.read().strip())
            # 9e18 is the common 'no limit' value for v1
            if val < 9000000000000000000:
                return val

    # 3. Fallback: Physical System Memory
    return psutil.virtual_memory().total


def get_used_memory():
    """Returns the current memory usage in bytes, respecting container bounds."""
    # Cgroup v2 usage
    if os.path.exists("/sys/fs/cgroup/memory.current"):
        with open("/sys/fs/cgroup/memory.current", "r") as f:
            return int(f.read().strip())

    # Cgroup v1 usage
    if os.path.exists("/sys/fs/cgroup/memory/memory.usage_in_bytes"):
        with open("/sys/fs/cgroup/memory/memory.usage_in_bytes", "r") as f:
            return int(f.read().strip())

    # Fallback: System-wide used memory
    vm = psutil.virtual_memory()
    return vm.total - vm.available


MemSymbol = Literal["K", "M", "G", "T", "P", "E", "Z", "Y"]
"""supported symbols for memory rounding"""
_MEM_SYMBOLS: tuple[MemSymbol, ...] = get_args(MemSymbol)


def bytes2human(n, max_round: MemSymbol = "Y"):
    """
    Convert bytes to something human readable

    https://psutil.readthedocs.io/en/latest/#recipes
    http://code.activestate.com/recipes/578019
    >>> bytes2human(10000)
    '9.8K'
    >>> bytes2human(100001221)
    '95.4M'

    max_round -  the highest level of rounding that will be done. Defaults to yobibyte
    """
    available_symbols = _MEM_SYMBOLS[: 1 + _MEM_SYMBOLS.index(max_round)]

    prefix = {}
    for i, sym in enumerate(available_symbols):
        prefix[sym] = 1 << (i + 1) * 10
    for sym in reversed(available_symbols):
        if n >= prefix[sym]:
            value = float(n) / prefix[sym]
            return f"{value:.1f}{sym}"
    return f"{n}B"


def meminfo(max_round: MemSymbol | None = "M"):
    """
    return a dict describing the current state of system memory included
    swap, mem, used_swap, used_mem. Does not respect container boundaries.

    max_round - if not none then round the results to the requested byte size.
        results will be strings. If None then return memory in bytes as ints
    """
    vm = psutil.virtual_memory()
    sm = psutil.swap_memory()

    process = psutil.Process(os.getpid())
    process_mem = process.memory_info().rss

    return {
        "procmem": (
            bytes2human(process_mem, max_round=max_round) if max_round is not None else process_mem
        ),
        "sysmem": (
            bytes2human(vm.total, max_round=max_round) if max_round is not None else vm.total
        ),
        "used_sysmem": (
            bytes2human(vm.used, max_round=max_round) if max_round is not None else vm.used
        ),
        "pct_sysmem": vm.percent,
        "sysswap": (
            bytes2human(sm.total, max_round=max_round) if max_round is not None else sm.total
        ),
        "used_sysswap": (
            bytes2human(sm.used, max_round=max_round) if max_round is not None else sm.used
        ),
        "pct_sysswap": sm.percent,
    }


def get_size_recursive(obj):
    """Recursively find size of objects"""

    size = sys.getsizeof(obj)

    if isinstance(obj, dict):
        # iterate through dict contents
        for key, value in obj.items():
            size += get_size_recursive(key)
            size += get_size_recursive(value)
        return size

    type_str = str(type(obj))
    if (
        hasattr(obj, "__iter__")
        and not isinstance(obj, (str, bytes))
        and "DataFrame" not in type_str
    ):
        # iterate through iterable objects, except pandas dataframe
        for item in obj:
            size += get_size_recursive(item)
        return size

    if "DataFrame" in type_str:
        # use pandas memory usage method
        size += obj.memory_usage(deep=True).sum()
        return size

    if not isinstance(obj, (int, bool, float, str, Enum, Callable)) and obj is not None:
        log.get_logger(__name__).limited_warning(
            f"Don't know how to recursively get the size of objects of type {type(obj)}"
        )

    return size
