import sys
import time
import argparse

from . import sqlalchemy
from .attribute_object import AttributeObject
from .base_test_class import BaseTestClass
from .deep_compare import (deep_compare, deep_compare_dicts, deep_compare_objs,
                           compare_dataframes, deep_compare_ordered_collections)
from .json import make_json_compatible


def process_timer(timed_func):
    """
    decorator that prints the running time for the function it decorates.
    """
    def wrapper(*args, **kwargs):
        _start = time.perf_counter()
        try:
            result = timed_func(*args, **kwargs)
        finally:
            print("{} secs elapsed".format(round(time.perf_counter() - _start, 5)),
                  file=sys.stderr)
        return result

    return wrapper


class ArgumentDefaultsHelpNoNoneFormatter(argparse.HelpFormatter):
    """
    Add the default for an argument to its help if the default is not None
    Based on the implementation of argparse.ArgumentDefaultsHelpNoNoneFormatter
    """

    def _get_help_string(self, action):
        help = action.help
        if '%(default)' not in action.help:
            if action.default not in (argparse.SUPPRESS, None):
                defaulting_nargs = [argparse.OPTIONAL, argparse.ZERO_OR_MORE]
                if action.option_strings or action.nargs in defaulting_nargs:
                    help += ' (default: %(default)s)'
        return help
