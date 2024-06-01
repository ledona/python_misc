import argparse
import hashlib
import pickle

from . import sqlalchemy
from .base_test_class import BaseTestClass
from .deep_compare import (
    compare_dataframes,
    deep_compare,
    deep_compare_dicts,
    deep_compare_objs,
    deep_compare_ordered_collections,
)
from .json import make_json_compatible
from .profiler import process_timer, profileit, ctx_timer


def constant_hasher(obj, as_int=True):
    """
    return a constant (from one python run to the next) hash value for obj
    note that the obj's repr is what is actually hashed
    """
    hash_arg = pickle.dumps(obj)
    hash_val = hashlib.md5(hash_arg)
    return int.from_bytes(hash_val.digest(), "big") if as_int else hash_val.hexdigest()


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


__all__ = [
    "sqlalchemy",
    "BaseTestClass",
    "ctx_timer",
    "deep_compare",
    "deep_compare_dicts",
    "deep_compare_objs",
    "compare_dataframes",
    "deep_compare_ordered_collections",
    "make_json_compatible",
    "profileit",
    "constant_hasher",
    "process_timer",
    "ArgumentDefaultsHelpNoNoneFormatter",
]
