"""
function decorator that profiles the decorated function. based on
https://stackoverflow.com/questions/5375624/a-decorator-that-profiles-a-method-call-and-logs-the-profiling-result
"""

import cProfile
import pstats
from typing import Callable, Collection, TypeVar, Any, cast


F = TypeVar("F", bound=Callable[..., Any])


def profileit(
    output_filename: str | None = None,
    sort_by="cumtime",
    print_restrictions: Collection | None = (0.1,),
):
    """
    decorator that profiles the wrapped functionchain

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
