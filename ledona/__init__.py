import sys
import time


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
                print("{} secs elapsed".format(round(time.perf_counter() - _start, 5)))
            return result

        return wrapper
    else:
        return timed_func
