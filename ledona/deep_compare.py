from typing import Optional, Iterable
from enum import Enum

import pandas


def deep_compare(first, second, msg=None, assert_tests=True) -> bool:
    """
    return - true if the first and second args are comparable
    raises - AssertionError is assert_tests is True and the first and second args are not equivalent
    """
    if not __debug__ and assert_tests is True:
        raise ValueError("assert_tests cannot be true in optimized/non debug mode")

    if isinstance(first, pandas.DataFrame):
        return compare_dataframes(first, second, msg=msg, assert_tests=assert_tests)
    elif hasattr(first, '__dict__') and not isinstance(first, Enum):
        return deep_compare_objs(first, second, msg=(msg or ""), assert_tests=assert_tests)
    elif hasattr(first, '_fields'):
        # must be a named tuple...
        return deep_compare_objs(first, second, attr_names=first._fields, msg=(msg or ""),
                                 assert_tests=assert_tests)
    elif isinstance(first, dict):
        return deep_compare_dicts(first, second, msg=(msg or ""), assert_tests=assert_tests)
    elif isinstance(first, (list, tuple)):
        deep_compare_ordered_collections(first, second, msg=(msg or ""),
                                         assert_tests=assert_tests)
    else:
        try:
            assert first == second, msg
        except AssertionError:
            if assert_tests:
                raise
            else:
                return False

    return True


def compare_dataframes(df1: pandas.DataFrame, df2: pandas.DataFrame,
                       cols: Optional[Iterable[str]] = None,
                       msg: Optional[str] = None,
                       ignore_col_order: bool = False,
                       ignore_row_order: bool = True,
                       ignore_index: bool = False,
                       assert_tests: bool = True) -> bool:
    """
    compare 2 dataframes, column types must match, expect an error with 'dtype' are different
    if column types don't match

    ignore_index - if true then dataframe indices will be reset, and the old index will be
       dropped before comparing
    ignore_col_order - if True then the order of the columns must match
    ignore_row_order - if true then both dataframes will be sorted before comparison
    cols - Only compare these columns of data, otherwise both dataframes must have the same
       columns
    assert_tests - if an internal comparison fails then raise an AssertionError (this allows for the
                   specific inequality to be surfaced)
    returns - true if they are equivalent, false if not (if assert_tests is True then an inequality will
              result in an AssertionError instead of a returned False)
    """
    if not __debug__ and assert_tests is True:
        raise ValueError("assert_tests cannot be true in optimized/non debug mode")

    assert isinstance(df1, pandas.DataFrame)
    assert isinstance(df2, pandas.DataFrame)

    if cols is not None:
        # trim the result to the columns to test
        for col_name in df1.columns:
            if col_name not in cols:
                df1 = df1.drop(col_name, 1)

        for col_name in df2.columns:
            if col_name not in cols:
                df2 = df2.drop(col_name, 1)

    if ignore_col_order is True:
        # sort both by column name
        df1 = df1[sorted(df1.columns)]
        df2 = df2[sorted(df2.columns)]

    # sort the dataframes
    if ignore_row_order is True:
        df1 = df1.reindex(sorted(df1.columns), axis=1)
        df2 = df2.reindex(sorted(df2.columns), axis=1)

    if ignore_index is True:
        df1 = df1.reset_index(drop=True)
        df2 = df2.reset_index(drop=True)

    try:
        assert df1.columns.tolist() == df2.columns.tolist(), \
            ((msg + " :: ") if msg is not None else "") + "column names don't match"

        pandas.util.testing.assert_frame_equal(df1, df2, check_names=True, obj=msg)
    except AssertionError:
        if assert_tests:
            raise
        else:
            return False

    return True


def deep_compare_objs(obj1, obj2, attr_names=None, msg="", assert_tests=True) -> bool:
    """
    if attr_names is not provided, then obj1 must implement __dict__ and return
    a list of attributes via the vars() built-in function
    """
    if not __debug__ and assert_tests is True:
        raise ValueError("assert_tests cannot be true in optimized/non debug mode")

    if attr_names is None:
        attr_names = vars(obj1)

    try:
        for attr_name in attr_names:
            assert hasattr(obj1, attr_name), \
                f"{msg}: obj1 does not have attribute '{attr_name}'"
            assert hasattr(obj2, attr_name), \
                f"{msg}: obj2 does not have attribute '{attr_name}'"

            deep_compare(getattr(obj1, attr_name),
                         getattr(obj2, attr_name),
                         assert_tests=True,
                         msg=msg + f" >> obj1.{attr_name} != obj2.{attr_name}")
    except AssertionError:
        if assert_tests:
            raise
        else:
            return False

    return True


def deep_compare_ordered_collections(objs1, objs2, msg="", assert_tests=True):
    if not __debug__ and assert_tests is True:
        raise ValueError("assert_tests cannot be true in optimized/non debug mode")

    try:
        assert len(objs1) == len(objs2), \
            msg + ": lengths do not match. objs1 has length {}, objs2 has length {}".format(
                len(objs1), len(objs2))
        for i, (obj1, obj2) in enumerate(zip(objs1, objs2)):
            deep_compare(obj1, obj2, msg=msg + f": items {i} don't match")
    except AssertionError:
        if assert_tests:
            raise
        else:
            return False

    return True


def deep_compare_dicts(dict1, dict2, msg="", key_names=None, assert_tests=True, minimal_key_test=False):
    """
    assert_tests: if true then comparison failures will raise assertion errors
    minimal_test: if true then only compare values for keys in key_names, or if key_names is None
       only compare values for keys in dict1. all other keys are ignored

    returns: true if the dicts match, false otherwise
    raises ValueError if testing is true and a mismatch is found
    """
    if not __debug__ and assert_tests is True:
        raise ValueError("assert_tests cannot be true in optimized/non debug mode")

    assert isinstance(dict1, dict)
    assert isinstance(dict2, dict)

    if msg is not None:
        msg += " :: "

    try:
        if key_names is None:
            key_names_set = set(dict1.keys())
        else:
            key_names_set = set(key_names)

        if minimal_key_test:
            assert key_names_set <= set(dict1.keys()), \
                msg + ": dict1 does not have keys {}".format(key_names_set - set(dict1.keys()))
            assert key_names_set <= set(dict2.keys()), \
                msg + ": dict2 does not have key {}".format(key_names_set - set(dict2.keys()))

        for key_name in key_names_set:
            deep_compare(dict1[key_name], dict2[key_name],
                         assert_tests=True,
                         msg=msg + "dict1['{key_name}'] != dict2['{key_name}']".format(key_name=key_name))
    except AssertionError:
        if assert_tests:
            raise
        else:
            return False

    return True
