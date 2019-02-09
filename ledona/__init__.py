import sys
import time

from . import sqlalchemy
from .attribute_object import AttributeObject
from .base_test_class import BaseTestClass
from .deep_compare import (deep_compare, deep_compare_dicts, deep_compare_objs,
                           compare_dataframes, deep_compare_ordered_collections)
from .json import make_json_compatible


def process_timer(timed_func):
    """
    decorator that prints the running time for the function it decorates. disabled when
    nose is being run
    """
    if 'nose' not in sys.modules.keys():
        def wrapper(*args, **kwargs):
            _start = time.perf_counter()
            try:
                result = timed_func(*args, **kwargs)
            finally:
                print("{} secs elapsed".format(round(time.perf_counter() - _start, 5)),
                      file=sys.stderr)
            return result

        return wrapper
    else:
        return timed_func
