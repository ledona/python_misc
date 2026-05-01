"""container aware top for [C+G]PU/MEMORY usage created mostly with claudecode"""

import argparse
import curses
import getpass
import math
import os
import socket
import subprocess
import time
from typing import NamedTuple, Optional

_CGROUP_V1_CPUACCT = "/sys/fs/cgroup/cpuacct/cpuacct.usage_percpu"
_CGROUP_V1_CPU_QUOTA = "/sys/fs/cgroup/cpu/cpu.cfs_quota_us"
_CGROUP_V1_CPU_PERIOD = "/sys/fs/cgroup/cpu/cpu.cfs_period_us"
_CGROUP_V1_MEM_USAGE = "/sys/fs/cgroup/memory/memory.usage_in_bytes"
_CGROUP_V1_MEM_LIMIT = "/sys/fs/cgroup/memory/memory.limit_in_bytes"
_CGROUP_V2_CPUSET_EFF = "/sys/fs/cgroup/cpuset.cpus.effective"
_CGROUP_V2_CPU_MAX = "/sys/fs/cgroup/cpu.max"
_CGROUP_V2_MEM_CURR = "/sys/fs/cgroup/memory.current"

# EMA smoothing factor (higher = more responsive, lower = smoother)
_EMA_ALPHA = 0.3

# Color pair indices
_CP_DIM = 1  # gray:   <5%
_CP_GREEN = 2  # green:  5-40%
_CP_YELLOW = 3  # yellow: 40-90%
_CP_RED = 4  # red:    >90%

_SPARK_CHARS = "▁▂▃▄▅▆▇█"


def _parse_cpuset(s: str) -> list[int]:
    """Parse cpuset string like '0-3,6' into sorted list of core indices."""
    cores = []
    for part in s.strip().split(","):
        if "-" in part:
            a, b = part.split("-")
            cores.extend(range(int(a), int(b) + 1))
        else:
            cores.append(int(part))
    return sorted(cores)


def _fmt_cores(cores: list[int]) -> str:
    """Format sorted core list as compact ranges, e.g. [0,1,2,3,6] -> '0-3,6'."""
    if not cores:
        return ""
    parts = []
    start = end = cores[0]
    for c in cores[1:]:
        if c == end + 1:
            end = c
        else:
            parts.append(f"{start}-{end}" if start != end else str(start))
            start = end = c
    parts.append(f"{start}-{end}" if start != end else str(start))
    return ",".join(parts)


def _fmt_bytes(n: int, decimals: int = 1) -> str:
    v: float = n
    if n == 0:
        return "0.0"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if v < 1024:
            return f"{v:.{decimals}f}{unit}"
        v /= 1024
    return f"{v:.{decimals}f}PB"


def _fmt_pct(pct: float) -> str:
    if 0.2 <= pct < 1:
        return " <1%"
    return f"{round(pct):3d}%"


def _bar(pct: float, width: int) -> str:
    if round(pct) >= 100:
        return "|" * width
    filled = int(pct / 100 * width)
    return "|" * filled + "." * (width - filled)


def _color_attr(pct: float) -> int:
    if pct < 5:
        return curses.color_pair(_CP_DIM) | curses.A_DIM
    if pct < 40:
        return curses.color_pair(_CP_GREEN)
    if pct < 90:
        return curses.color_pair(_CP_YELLOW)
    return curses.color_pair(_CP_RED)


def _draw_bar(stdscr: curses.window, row: int, col: int, label: str, bar_width: int, pct: float):
    """Draw: LABEL [BAR] NNN%  with bar colored by pct threshold."""
    try:
        stdscr.addstr(row, col, f"{label} [")
        stdscr.addstr(_bar(pct, bar_width), _color_attr(pct))
        stdscr.addstr(f"] {_fmt_pct(pct)}")
    except curses.error:
        pass


def _spark_chars(values: list[float], bar_width: int, max_history: int) -> list[tuple[str, float]]:
    """Map history values onto bar_width sparkline characters.

    The full history window is max_history seconds wide. Characters on the left
    are blank until enough samples have been collected to fill that window.
    When max_history > bar_width multiple samples are averaged per character;
    when max_history < bar_width each sample is stretched across multiple characters.
    """
    n = len(values)
    # how many leading time-slots in the history window have no data yet
    empty_slots = max_history - n
    result = []
    for i in range(bar_width):
        # time-slot range [t0, t1) this character covers within the history window
        t0 = i * max_history / bar_width
        t1 = (i + 1) * max_history / bar_width
        # convert to indices into values[] (which holds the newest n slots)
        si = int(t0) - empty_slots
        ei = int(t1) - empty_slots
        if ei <= si:
            ei = si + 1
        if ei <= 0 or si >= n:
            result.append((" ", 0.0))
            continue
        chunk = values[max(0, si) : min(n, ei)]
        pct = sum(chunk) / len(chunk) if chunk else 0.0
        idx = min(len(_SPARK_CHARS) - 1, round(pct / 100 * (len(_SPARK_CHARS) - 1)))
        result.append((_SPARK_CHARS[idx], pct))
    return result


def _fmt_uptime_secs(secs: int) -> str:
    days, rem = divmod(secs, 86400)
    hours, rem = divmod(rem, 3600)
    mins = rem // 60
    if days:
        return f"up {days}d {hours}h {mins}m"
    if hours:
        return f"up {hours}h {mins}m"
    return f"up {mins}m"


def _fmt_uptime() -> str:
    try:
        with open("/proc/uptime") as f:
            secs = int(float(f.read().split()[0]))
    except OSError:
        return "up ?"
    return _fmt_uptime_secs(secs)


def _fmt_container_uptime() -> str:
    """Estimate container uptime from PID 1 start time relative to host boot."""
    try:
        with open("/proc/uptime") as f:
            host_uptime = float(f.read().split()[0])
        with open("/proc/1/stat") as f:
            content = f.read()
        # comm field (field 2) may contain spaces/parens; find last ')' to safely split
        fields_after = content[content.rfind(")") + 2:].split()
        # starttime is field 22 in /proc/pid/stat (1-indexed), index 19 after comm+state
        starttime_ticks = int(fields_after[19])
        clk_tck = os.sysconf("SC_CLK_TCK")
        secs = max(0, int(host_uptime - starttime_ticks / clk_tck))
    except (OSError, IndexError, ValueError):
        return _fmt_uptime()
    return _fmt_uptime_secs(secs)


def _ruler(bar_width: int, max_history: int) -> str:
    """Build a dash-filled time axis of length bar_width with quarter-interval tick labels."""
    secs = sorted(
        {max_history, max_history * 3 // 4, max_history // 2, max_history // 4, 0}, reverse=True
    )
    ticks = []
    for s in secs:
        label = "now" if s == 0 else f"{s}s"
        pos = bar_width - len(label) if s == 0 else int((max_history - s) / max_history * bar_width)
        ticks.append((pos, label))
    ticks.sort()

    buf = ["-"] * bar_width
    last_end = -1
    for pos, label in ticks:
        if pos <= last_end or pos + len(label) > bar_width:
            continue
        for j, ch in enumerate(label):
            buf[pos + j] = ch
        last_end = pos + len(label)
    return "".join(buf)


def _draw_sparkline(
    stdscr: curses.window,
    row: int,
    col: int,
    label: str,
    values: list[float],
    bar_width: int,
    max_history: int,
):
    """Draw: LABEL [sparkline]"""
    try:
        stdscr.addstr(row, col, f"{label} [")
        spark_col = col + len(label) + 2
        for i, (ch, pct) in enumerate(_spark_chars(values, bar_width, max_history)):
            stdscr.addstr(row, spark_col + i, ch, _color_attr(pct))
        stdscr.addstr(row, spark_col + bar_width, "]")
    except curses.error:
        pass


class _GpuSample(NamedTuple):
    index: int
    name: str
    mem_used_mb: int
    mem_total_mb: int
    util_pct: float


def _sample_gpus() -> list[_GpuSample]:
    """Query nvidia-smi for per-GPU stats. Returns empty list if unavailable."""
    try:
        out = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=index,name,memory.used,memory.total,utilization.gpu",
                "--format=csv,noheader,nounits",
            ],
            stderr=subprocess.DEVNULL,
            timeout=5,
        ).decode()
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return []
    gpus = []
    for line in out.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) != 5:
            continue
        try:
            gpus.append(
                _GpuSample(
                    index=int(parts[0]),
                    name=parts[1],
                    mem_used_mb=int(parts[2]),
                    mem_total_mb=int(parts[3]),
                    util_pct=float(parts[4]),
                )
            )
        except ValueError:
            continue
    return gpus


def _read_proc_stat() -> dict[int, tuple[int, int]]:
    """Read /proc/stat, return {core_id: (idle_jiffies, total_jiffies)}."""
    result = {}
    with open("/proc/stat") as f:
        for line in f:
            if line.startswith("cpu") and len(line) > 3 and line[3].isdigit():
                parts = line.split()
                core_id = int(parts[0][3:])
                vals = [int(x) for x in parts[1:]]
                idle = vals[3] + (vals[4] if len(vals) > 4 else 0)  # idle + iowait
                result[core_id] = (idle, sum(vals))
    return result


class _Monitor:
    def __init__(self, history_seconds: int):
        self._cgroup_base: str = self._find_cgroup_base()
        self.cgroup_ver: Optional[int] = self._detect_cgroup()
        self.cpu_quota_cores: Optional[float] = self._get_cpu_quota()
        self.assigned_cores, _cores_known, self._is_cpuset_restricted = self._get_assigned_cores()
        # quota slicing only applies when cpuset pins the container to specific cores
        if self._is_cpuset_restricted and self.cpu_quota_cores is not None and len(self.assigned_cores) > math.ceil(self.cpu_quota_cores):
            self.display_cores = self.assigned_cores[: math.ceil(self.cpu_quota_cores)]
        else:
            self.display_cores = self.assigned_cores
        # show per-core bars only when we can be confident bars represent the
        # container's actual cores: cpuset-pinned, or quota/allocation covers all host cores
        if not _cores_known:
            self.per_core_accurate = False
            self._per_core_hide_reason = "cgroup cpuset controller present but its configuration could not be read"
        elif not self._is_cpuset_restricted and self.cpu_quota_cores is not None:
            # quota without cpuset: safe to show only if quota covers all host cores
            # (when not restricted, assigned_cores == all host cores)
            host_core_count = len(self.assigned_cores)
            if math.ceil(self.cpu_quota_cores) >= host_core_count:
                self.per_core_accurate = True
                self._per_core_hide_reason = ""
            else:
                self.per_core_accurate = False
                self._per_core_hide_reason = (
                    f"container quota is {math.ceil(self.cpu_quota_cores)} cores but host has "
                    f"{host_core_count}; cannot determine which specific cores are assigned"
                )
        else:
            self.per_core_accurate = True
            self._per_core_hide_reason = ""
        self._smoothed: dict[int, float] = {}
        self.hostname = socket.gethostname()
        self.username = getpass.getuser()
        self.max_history = history_seconds
        self._cpu_history: list[float] = []
        self._mem_history: list[float] = []
        _initial_gpus = _sample_gpus()
        self.gpu_names: dict[int, str] = {g.index: g.name for g in _initial_gpus}
        self._gpu_util_history: list[float] = []
        self._gpu_mem_history: list[float] = []
        self.cpu_model: Optional[str] = self._get_cpu_model()

    @staticmethod
    def _find_cgroup_base() -> str:
        """Return this process's own cgroup directory; falls back to /sys/fs/cgroup."""
        try:
            with open("/proc/self/cgroup") as f:
                for line in f:
                    parts = line.strip().split(":", 2)
                    if parts[0] == "0" and len(parts) == 3:
                        rel = parts[2].strip()
                        if rel and rel != "/":
                            candidate = "/sys/fs/cgroup" + rel
                            if os.path.isdir(candidate):
                                return candidate
        except OSError:
            pass
        return "/sys/fs/cgroup"

    @staticmethod
    def _find_v1_controller_path(controller: str) -> Optional[str]:
        """Return container-specific v1 cgroup directory for the given controller."""
        try:
            with open("/proc/self/cgroup") as f:
                for line in f:
                    parts = line.strip().split(":", 2)
                    if len(parts) == 3 and controller in parts[1].split(","):
                        rel = parts[2].strip()
                        if rel and rel != "/":
                            path = f"/sys/fs/cgroup/{controller}{rel}"
                            if os.path.isdir(path):
                                return path
        except OSError:
            pass
        return None

    def _detect_cgroup(self) -> Optional[int]:
        if os.path.exists(_CGROUP_V1_CPUACCT):
            return 1
        base = self._cgroup_base
        if any(os.path.exists(os.path.join(base, f)) for f in ("memory.current", "cpuset.cpus.effective", "cpu.max")):
            return 2
        if any(os.path.exists(p) for p in (_CGROUP_V2_MEM_CURR, _CGROUP_V2_CPUSET_EFF, _CGROUP_V2_CPU_MAX)):
            return 2
        return None

    def _get_cpu_quota(self) -> Optional[float]:
        """Return effective CPU count from cgroup quota, or None if unlimited/unavailable."""
        try:
            if self.cgroup_ver == 2:
                path = os.path.join(self._cgroup_base, "cpu.max")
                if os.path.exists(path):
                    parts = open(path).read().strip().split()
                    if parts[0] != "max":
                        return int(parts[0]) / int(parts[1])
            if self.cgroup_ver == 1:
                v1_cpu_path = self._find_v1_controller_path("cpu")
                quota_file = os.path.join(v1_cpu_path, "cpu.cfs_quota_us") if v1_cpu_path else _CGROUP_V1_CPU_QUOTA
                period_file = os.path.join(v1_cpu_path, "cpu.cfs_period_us") if v1_cpu_path else _CGROUP_V1_CPU_PERIOD
                if os.path.exists(quota_file):
                    quota = int(open(quota_file).read().strip())
                    if quota > 0:
                        period = 100000
                        if os.path.exists(period_file):
                            period = int(open(period_file).read().strip())
                        return quota / period
        except (OSError, ValueError, IndexError):
            pass
        return None

    @staticmethod
    def _get_cpu_model() -> Optional[str]:
        try:
            with open("/proc/cpuinfo") as f:
                for line in f:
                    if line.startswith("model name"):
                        name = line.split(":", 1)[1].strip()
                        if " @" in name:
                            name = name[: name.index(" @")]
                        name = name.replace("(R)", "").replace("(TM)", "")
                        return " ".join(name.split())
        except OSError:
            pass
        return None

    def _get_assigned_cores(self) -> tuple[list[int], bool, bool]:
        """Return (cores, cores_known, is_restricted).

        cores_known: True when the full set of cores available to this container is
        confirmed (bare metal, no cpuset restriction, or cpuset successfully read).
        False only when a cpuset controller is present but its file is unreadable,
        so we cannot determine whether the container is pinned to a subset.

        is_restricted: True when cores is a cpuset-pinned strict subset of all host
        cores.  Used to decide quota slicing and avg_cpu formula.
        """
        all_cores = sorted(_read_proc_stat().keys())
        if self.cgroup_ver is None:
            return all_cores, True, False  # bare metal: all cores, confirmed

        all_core_set = set(all_cores)

        if self.cgroup_ver == 1:
            v1_path = self._find_v1_controller_path("cpuset")
            if v1_path:
                try:
                    with open(os.path.join(v1_path, "cpuset.cpus")) as f:
                        cores = _parse_cpuset(f.read())
                    return cores, True, set(cores) < all_core_set
                except OSError:
                    # controller present but file unreadable: cannot determine restriction
                    return all_cores, False, False

        # Check v2 cpuset files (pure v2 or hybrid fallback)
        base = self._cgroup_base
        for fname in ("cpuset.cpus.effective", "cpuset.cpus"):
            path = os.path.join(base, fname)
            if not os.path.exists(path):
                continue
            try:
                with open(path) as f:
                    content = f.read().strip()
            except OSError:
                continue
            if not content:
                continue
            cores = _parse_cpuset(content)
            return cores, True, set(cores) < all_core_set

        # No cpuset restriction detected: all cores confirmed available
        return all_cores, True, False

    def _sample_cpu(self):
        if self.cgroup_ver == 1:
            v1_path = self._find_v1_controller_path("cpuacct")
            cpuacct_file = os.path.join(v1_path, "cpuacct.usage_percpu") if v1_path else _CGROUP_V1_CPUACCT
            with open(cpuacct_file) as f:
                return [int(x) for x in f.read().split()]
        return _read_proc_stat()

    def _calc_pct(self, s1, s2, elapsed_ns: float) -> dict[int, float]:
        pcts = {}
        if self.cgroup_ver == 1:
            for core in self.assigned_cores:
                if core < len(s1) and core < len(s2):
                    pcts[core] = max(0.0, min(100.0, (s2[core] - s1[core]) / elapsed_ns * 100))
        else:
            for core in self.assigned_cores:
                if core not in s1 or core not in s2:
                    continue
                d_total = s2[core][1] - s1[core][1]
                d_idle = s2[core][0] - s1[core][0]
                if d_total <= 0:
                    pcts[core] = 0.0
                else:
                    pcts[core] = max(0.0, min(100.0, (1 - d_idle / d_total) * 100))
        return pcts

    def _smooth(self, pcts: dict[int, float]) -> dict[int, float]:
        for core, pct in pcts.items():
            if core in self._smoothed:
                self._smoothed[core] = _EMA_ALPHA * pct + (1 - _EMA_ALPHA) * self._smoothed[core]
            else:
                self._smoothed[core] = pct
        return self._smoothed

    def _calc_avg_cpu(self, pcts: dict[int, float]) -> float:
        """Compute avg CPU % scaled to quota or cpuset, whichever applies."""
        if not self._is_cpuset_restricted and self.cpu_quota_cores:
            # quota is the binding constraint: normalize by quota (gives % of quota consumed)
            return min(100.0, sum(pcts.get(c, 0.0) for c in self.assigned_cores) / self.cpu_quota_cores)
        cores = self.display_cores
        return sum(pcts.get(c, 0.0) for c in cores) / len(cores) if cores else 0.0

    def _record_history(self, avg_cpu: float, mem_pct: float):
        self._cpu_history.append(avg_cpu)
        if len(self._cpu_history) > self.max_history:
            self._cpu_history = self._cpu_history[-self.max_history :]
        self._mem_history.append(mem_pct)
        if len(self._mem_history) > self.max_history:
            self._mem_history = self._mem_history[-self.max_history :]

    def _record_gpu_history(self, gpus: list[_GpuSample]):
        if not gpus:
            return
        avg_util = sum(g.util_pct for g in gpus) / len(gpus)
        total_mb = sum(g.mem_total_mb for g in gpus)
        used_mb = sum(g.mem_used_mb for g in gpus)
        mem_pct = used_mb / total_mb * 100 if total_mb else 0.0
        self._gpu_util_history.append(avg_util)
        if len(self._gpu_util_history) > self.max_history:
            self._gpu_util_history = self._gpu_util_history[-self.max_history :]
        self._gpu_mem_history.append(mem_pct)
        if len(self._gpu_mem_history) > self.max_history:
            self._gpu_mem_history = self._gpu_mem_history[-self.max_history :]

    @staticmethod
    def _system_mem_total() -> Optional[int]:
        try:
            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        return int(line.split()[1]) * 1024
        except OSError:
            pass
        return None

    @staticmethod
    def _system_swap() -> tuple[int, int]:
        """Returns (swap_used, swap_total) from /proc/meminfo."""
        total = free = 0
        try:
            with open("/proc/meminfo") as f:
                for line in f:
                    parts = line.split()
                    if parts[0] == "SwapTotal:":
                        total = int(parts[1]) * 1024
                    elif parts[0] == "SwapFree:":
                        free = int(parts[1]) * 1024
        except OSError:
            pass
        return total - free, total

    def _get_swap(self) -> tuple[int, int]:
        """Returns (swap_used_bytes, swap_total_bytes)."""
        try:
            if self.cgroup_ver == 2:
                base = self._cgroup_base
                swap_curr = os.path.join(base, "memory.swap.current")
                if os.path.exists(swap_curr):
                    with open(swap_curr) as f:
                        used = int(f.read().strip())
                    total = None
                    swap_max = os.path.join(base, "memory.swap.max")
                    if os.path.exists(swap_max):
                        with open(swap_max) as f:
                            content = f.read().strip()
                            if content != "max":
                                total = int(content)
                    _, sys_total = self._system_swap()
                    return used, total or sys_total or 1
            if self.cgroup_ver == 1 and os.path.exists(
                "/sys/fs/cgroup/memory/memory.memsw.usage_in_bytes"
            ):
                with open("/sys/fs/cgroup/memory/memory.memsw.usage_in_bytes") as f:
                    memsw_used = int(f.read().strip())
                with open(_CGROUP_V1_MEM_USAGE) as f:
                    mem_used = int(f.read().strip())
                _, sys_total = self._system_swap()
                return max(0, memsw_used - mem_used), sys_total or 1
        except OSError:
            pass
        return self._system_swap()

    @staticmethod
    def _get_disk() -> tuple[int, int]:
        """Returns (used_bytes, total_bytes) for the root filesystem."""
        try:
            st = os.statvfs("/")
            total = st.f_blocks * st.f_frsize
            used = (st.f_blocks - st.f_bfree) * st.f_frsize
            return used, total
        except OSError:
            return 0, 1

    def _get_memory(self) -> tuple[int, int]:
        """Returns (used_bytes, limit_bytes); limit falls back to system total."""
        try:
            if self.cgroup_ver == 1:
                with open(_CGROUP_V1_MEM_USAGE) as f:
                    used = int(f.read().strip())
                with open(_CGROUP_V1_MEM_LIMIT) as f:
                    limit_val = int(f.read().strip())
                limit = None if limit_val >= (1 << 62) else limit_val
            elif self.cgroup_ver == 2:
                base = self._cgroup_base
                curr_path = os.path.join(base, "memory.current")
                if not os.path.exists(curr_path):
                    return 0, self._system_mem_total() or 1
                with open(curr_path) as f:
                    used = int(f.read().strip())
                limit = None
                max_path = os.path.join(base, "memory.max")
                if os.path.exists(max_path):
                    with open(max_path) as f:
                        content = f.read().strip()
                        if content != "max":
                            limit = int(content)
            else:
                with open("/proc/meminfo") as f:
                    info = {}
                    for line in f:
                        parts = line.split()
                        if parts[0] in ("MemTotal:", "MemAvailable:"):
                            info[parts[0]] = int(parts[1]) * 1024
                total = info.get("MemTotal:", 1)
                avail = info.get("MemAvailable:", 0)
                return total - avail, total
        except OSError:
            return 0, self._system_mem_total() or 1
        return used, limit or self._system_mem_total() or 1

    def run(self, stdscr: curses.window):
        curses.curs_set(0)
        stdscr.nodelay(True)
        curses.start_color()
        curses.use_default_colors()
        curses.init_pair(_CP_DIM, curses.COLOR_WHITE, -1)
        curses.init_pair(_CP_GREEN, curses.COLOR_GREEN, -1)
        curses.init_pair(_CP_YELLOW, curses.COLOR_YELLOW, -1)
        curses.init_pair(_CP_RED, curses.COLOR_RED, -1)

        s1 = self._sample_cpu()
        t1 = time.monotonic()
        force_clear = False

        while True:
            time.sleep(1)
            t2 = time.monotonic()
            s2 = self._sample_cpu()

            pcts = self._calc_pct(s1, s2, (t2 - t1) * 1e9)
            smoothed = self._smooth(pcts)
            mem_used, mem_limit = self._get_memory()
            swap_used, swap_total = self._get_swap()
            disk_used, disk_total = self._get_disk()
            gpus = _sample_gpus()
            self._record_gpu_history(gpus)
            s1, t1 = s2, t2

            avg_cpu = self._calc_avg_cpu(smoothed)
            mem_pct = mem_used / mem_limit * 100
            swap_pct = swap_used / swap_total * 100 if swap_total else 0.0
            disk_pct = disk_used / disk_total * 100 if disk_total else 0.0
            self._record_history(avg_cpu, mem_pct)

            if force_clear:
                stdscr.clear()
                force_clear = False
            else:
                stdscr.erase()
            height, width = stdscr.getmaxyx()

            # Row 0: title left, datetime right
            now = time.strftime("%Y-%m-%d %H:%M:%S")
            try:
                stdscr.addstr(0, 0, "contop - container aware cpu/gpu/memory usage", curses.A_BOLD)
                if width > len(now) + 8:
                    stdscr.addstr(0, width - len(now) - 1, now)
            except curses.error:
                pass

            # Row 1: hostname left, uptime right
            uptime = ("ctr " + _fmt_container_uptime()) if self.cgroup_ver else ("host " + _fmt_uptime())
            try:
                stdscr.addstr(1, 0, f"{self.username}@{self.hostname}")
                if width > len(uptime) + 2:
                    stdscr.addstr(1, width - len(uptime) - 1, uptime)
            except curses.error:
                pass

            # Row 2: separator
            try:
                stdscr.addstr(2, 0, "╌" * (width - 1))
            except curses.error:
                pass

            # Row 3+: info section — labels in default color, values color-coded by threshold.
            # Each chunk (label + value) wraps to the next row if it won't fit.
            cgroup_str = f"cgroup v{self.cgroup_ver}" if self.cgroup_ver else "host"
            if self.cpu_quota_cores is not None:
                n_effective = math.ceil(self.cpu_quota_cores)
                cores_label = f"({n_effective} core)"
            else:
                cores_label = f"({len(self.assigned_cores)} core)"
            if self.cpu_model:
                cores_label += f" {self.cpu_model}"
            has_swap = swap_total >= 100 * 1024
            if has_swap:
                swap_val = f"{_fmt_bytes(swap_used)}/{_fmt_bytes(swap_total)} ({_fmt_pct(swap_pct)})"
                swap_attr: int | None = _color_attr(swap_pct)
            else:
                swap_val, swap_attr = "0 Swp", None
            # each chunk: list of (text, attr) drawn atomically — no wrapping mid-chunk;
            # None is a forced line break
            chunks: list[list[tuple[str, int | None]] | None] = [
                [(f"{cgroup_str}  |  {cores_label}: ", None), (_fmt_pct(avg_cpu), _color_attr(avg_cpu))],
                [("  |  Mem: ", None), (f"{_fmt_bytes(mem_used)}/{_fmt_bytes(mem_limit)} {_fmt_pct(mem_pct)}", _color_attr(mem_pct))],
                [("  |  Swap: ", None), (swap_val, swap_attr)],
                [("  |  Disk: ", None), (f"{_fmt_bytes(disk_used, 0)}/{_fmt_bytes(disk_total, 0)}", _color_attr(disk_pct))],
            ]
            if self.gpu_names:
                n_gpus = len(self.gpu_names)
                avg_gpu_util = sum(g.util_pct for g in gpus) / len(gpus) if gpus else 0.0
                total_vmem_mb = sum(g.mem_total_mb for g in gpus)
                used_vmem_mb = sum(g.mem_used_mb for g in gpus)
                vmem_pct = used_vmem_mb / total_vmem_mb * 100 if total_vmem_mb else 0.0
                unique_names = list(dict.fromkeys(self.gpu_names.values()))
                gpu_name_str = "/".join(unique_names)
                chunks.append(None)
                chunks.append([(f"{n_gpus}x {gpu_name_str}: ", None), (_fmt_pct(avg_gpu_util), _color_attr(avg_gpu_util))])
                chunks.append([("  |  VMem: ", None), (f"{_fmt_bytes(used_vmem_mb << 20)}/{_fmt_bytes(total_vmem_mb << 20)} {_fmt_pct(vmem_pct)}", _color_attr(vmem_pct))])
            cur_row, cur_col = 3, 0
            for chunk in chunks:
                if chunk is None:
                    cur_row += 1
                    cur_col = 0
                    continue
                chunk_len = sum(len(text) for text, _ in chunk)
                if cur_col > 0 and cur_col + chunk_len >= width - 1:
                    cur_row += 1
                    cur_col = 0
                for i, (text, attr) in enumerate(chunk):
                    if i == 0 and cur_col == 0 and text.startswith("  |  "):
                        text = text[5:]
                    try:
                        clipped = text[: max(0, width - 1 - cur_col)]
                        if attr is not None:
                            stdscr.addstr(cur_row, cur_col, clipped, attr)
                        else:
                            stdscr.addstr(cur_row, cur_col, clipped)
                        cur_col += len(clipped)
                    except curses.error:
                        pass

            # separator after info (moves down if info wrapped)
            sep_row = cur_row + 1
            try:
                stdscr.addstr(sep_row, 0, "╌" * (width - 1))
            except curses.error:
                pass

            row = sep_row + 1

            # Sparklines — same width as the memory bar below
            # label "CPU " (4) + " [" (2) + "]" (1) = 7 overhead
            bar_w_spark = max(10, width - 8)
            _draw_sparkline(
                stdscr, row, 0, "CPU ", self._cpu_history, bar_w_spark, self.max_history
            )
            row += 1
            _draw_sparkline(
                stdscr, row, 0, "Mem ", self._mem_history, bar_w_spark, self.max_history
            )
            row += 1
            if self.gpu_names:
                if row < height - 2:
                    _draw_sparkline(stdscr, row, 0, "GPU ", self._gpu_util_history, bar_w_spark, self.max_history)
                    row += 1
                if row < height - 2:
                    _draw_sparkline(stdscr, row, 0, "GMem", self._gpu_mem_history, bar_w_spark, self.max_history)
                    row += 1
            # ruler indented to align with bar content: label (4) + " [" (2) = 6
            try:
                stdscr.addstr(row, 6, _ruler(bar_w_spark, self.max_history))
            except curses.error:
                pass
            row += 2

            # CPU bars — only shown when per-core accuracy can be guaranteed (cpuset or bare metal)
            if self.per_core_accurate:
                n_cores = len(self.display_cores)
                n_cols = max(1, min(n_cores, width // 17))
                n_rows = (n_cores + n_cols - 1) // n_cols
                n_cols = (n_cores + n_rows - 1) // n_rows  # rebalance for even row fill
                col_width = width // n_cols
                bar_w_cpu = max(5, col_width - 12)

                for r in range(n_rows):
                    if row + r >= height - 2:
                        break
                    for c in range(n_cols):
                        core_idx = r + c * n_rows
                        if core_idx >= n_cores:
                            break
                        core = self.display_cores[core_idx]
                        _draw_bar(stdscr, row + r, c * col_width, f"{core_idx:3d}", bar_w_cpu, smoothed.get(core, 0.0))
                row += n_rows
            else:
                try:
                    stdscr.addstr(row, 0, f"per-core CPU usage unavailable: {self._per_core_hide_reason}", curses.A_DIM)
                except curses.error:
                    pass
                row += 1

            try:
                stdscr.addstr(min(height - 1, row + 1), 0, "q: quit  r: refresh")
            except curses.error:
                pass
            stdscr.refresh()

            key = stdscr.getch()
            if key in (ord("q"), ord("Q")):
                break
            if key in (ord("r"), ord("R")):
                force_clear = True


def _spot_state(monitor: _Monitor):
    """Print a one-time text snapshot of CPU, memory, swap, and disk state, then exit."""
    s1 = monitor._sample_cpu()
    t1 = time.monotonic()
    time.sleep(0.5)
    t2 = time.monotonic()
    s2 = monitor._sample_cpu()

    pcts = monitor._calc_pct(s1, s2, (t2 - t1) * 1e9)
    avg_cpu = monitor._calc_avg_cpu(pcts)

    mem_used, mem_limit = monitor._get_memory()
    mem_pct = mem_used / mem_limit * 100

    swap_used, swap_total = monitor._get_swap()
    swap_pct = swap_used / swap_total * 100 if swap_total else 0.0

    disk_used, disk_total = monitor._get_disk()
    disk_pct = disk_used / disk_total * 100 if disk_total else 0.0

    cgroup_str = f"cgroup v{monitor.cgroup_ver}" if monitor.cgroup_ver else "host"
    if monitor.cpu_quota_cores is not None:
        cores_str = f"{math.ceil(monitor.cpu_quota_cores)} cores (quota)"
    else:
        cores_str = f"{len(monitor.assigned_cores)} cores"

    uptime = _fmt_container_uptime() if monitor.cgroup_ver else _fmt_uptime()
    model_str = f" {monitor.cpu_model}," if monitor.cpu_model else ""
    print(f"CPU:    {round(avg_cpu):3d}%  ({cores_str},{model_str} {cgroup_str}, {uptime})")
    print(f"Memory: {_fmt_bytes(mem_used)} / {_fmt_bytes(mem_limit)} ({round(mem_pct):3d}%)")
    if swap_total >= 100 * 1024:
        print(f"Swap:   {_fmt_bytes(swap_used)} / {_fmt_bytes(swap_total)} ({round(swap_pct):3d}%)")
    else:
        print("Swap:   0 Swp")
    print(f"Disk:   {_fmt_bytes(disk_used, 0)} / {_fmt_bytes(disk_total, 0)} ({round(disk_pct):3d}%)")
    for g in _sample_gpus():
        mem_pct_g = g.mem_used_mb / g.mem_total_mb * 100 if g.mem_total_mb else 0.0
        print(
            f"GPU {g.index}: {g.name}  "
            f"util {round(g.util_pct):3d}%  "
            f"mem {g.mem_used_mb / 1024:.1f}GB / {g.mem_total_mb / 1024:.0f}GB ({round(mem_pct_g):3d}%)"
        )


def main():
    parser = argparse.ArgumentParser(description="Container-aware top with per-core CPU bars")
    parser.add_argument(
        "--history",
        type=int,
        default=120,
        metavar="SECONDS",
        help="seconds of history shown in sparklines (default: 120)",
    )
    parser.add_argument(
        "--spot-state",
        action="store_true",
        help="print a point-in-time summary of CPU, memory, swap, and disk, then exit",
    )
    args = parser.parse_args()

    monitor = _Monitor(history_seconds=args.history)
    if args.spot_state:
        _spot_state(monitor)
        return

    try:
        curses.wrapper(monitor.run)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
