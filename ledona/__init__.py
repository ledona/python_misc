import sys
import time
import argparse
from datetime import timedelta
import hashlib

from . import sqlalchemy
from .base_test_class import BaseTestClass
from .deep_compare import (
    deep_compare,
    deep_compare_dicts,
    deep_compare_objs,
    compare_dataframes,
    deep_compare_ordered_collections,
)
from .json import make_json_compatible


def constant_hasher(obj, as_int=True):
    """return a constant (from one python run to the next) hash value for obj"""
    hasher = hashlib.sha1()
    hasher.update(repr(obj).encode("utf-8"))
    return int(hasher.hexdigest(), 16) if as_int else hasher.hexdigest()


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


class ArgumentDefaultsHelpNoNoneFormatter(argparse.HelpFormatter):
    """
    Add the default for an argument to its help if the default is not None
    Based on the implementation of argparse.ArgumentDefaultsHelpNoNoneFormatter
    """

    def _get_help_string(self, action):
        help_ = action.help
        if "%(default)" not in action.help:
            if action.default not in (argparse.SUPPRESS, None):
                defaulting_nargs = [argparse.OPTIONAL, argparse.ZERO_OR_MORE]
                if action.option_strings or action.nargs in defaulting_nargs:
                    help_ += " (default: %(default)s)"
        return help_
