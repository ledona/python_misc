import cProfile
import pstats
import sys
import time
from contextlib import contextmanager
from datetime import timedelta
from logging import Logger
from typing import Any, Callable, Collection, TypeVar, cast, Literal

F = TypeVar("F", bound=Callable[..., Any])


def profileit(
    output_filename: str | None = None,
    sort_by="cumtime",
    print_restrictions: Collection | None = (0.1,),
):
    """
    decorator that profiles the wrapped functionchain
    https://stackoverflow.com/questions/5375624/a-decorator-that-profiles-a-method-call-and-logs-the-profiling-result

    print_restrictions - passed to pstats.print_stats to restrict which profile information
        to display. A numeric entry is used to retrict to the top N or N% of entries.
        Strings are used to filter for function names
    output_filename - filename to dump stat data. default is function name and a filename extention
        '.profile'
    """

    def inner(func: F) -> F:
        filename = output_filename or func.__name__ + ".profile"

        def wrapper(*args, **kwargs):
            print(f"*** Running cProfile on call to '{func}' ***")
            prof = cProfile.Profile()
            retval = prof.runcall(func, *args, **kwargs)

            print(f"*** Dumping profile stats for '{func}' to '{filename}'")
            prof.dump_stats(filename)
            stats = pstats.Stats(prof)
            stats.sort_stats(sort_by).print_stats(*print_restrictions)
            return retval

        return cast(F, wrapper)

    return inner


def process_timer(timed_func):
    """
    decorator that prints the running time for the function it decorates.
    """

    def wrapper(*args, **kwargs):
        _start = time.perf_counter()
        try:
            result = timed_func(*args, **kwargs)
        finally:
            elapsed = timedelta(seconds=round(time.perf_counter() - _start, 3))
            print(f"{elapsed} elapsed", file=sys.stderr)
        return result

    return wrapper


@contextmanager
def ctx_timer(
    msg: str | None = None,
    logger: None | Logger = None,
    msg_format: Literal["start-end", "end"] = "start-end",
):
    """process timer as a context manager"""
    log_func = logger.info if logger else print
    if "start" in msg_format:
        log_func("Starting timed execution %s", f": {msg}" if msg else "")
    _start = time.perf_counter()
    yield
    elapsed = timedelta(seconds=round(time.perf_counter() - _start, 3))
    log_func("Finished timed execution %s elapsed time %s", f": {msg}" if msg else "", elapsed)
