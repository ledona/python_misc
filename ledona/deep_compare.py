from typing import Iterable
from enum import Enum

import pandas as pd


def deep_compare(first, second, msg=None, assert_tests=True) -> bool:
    """
    return - true if the first and second args are comparable
    raises - AssertionError is assert_tests is True and the first and second args are not equivalent
    """
    if not __debug__ and assert_tests is True:
        raise ValueError("assert_tests cannot be true in optimized/non debug mode")

    if isinstance(first, pd.DataFrame):
        return compare_dataframes(first, second, msg=msg, assert_tests=assert_tests)
    if hasattr(first, "__dict__") and not isinstance(first, Enum):
        return deep_compare_objs(first, second, msg=(msg or ""), assert_tests=assert_tests)
    if hasattr(first, "_fields"):
        # must be a named tuple...
        return deep_compare_objs(
            first,
            second,
            attr_names=first._fields,
            msg=(msg or ""),
            assert_tests=assert_tests,
        )
    if isinstance(first, dict):
        return deep_compare_dicts(first, second, msg=(msg or ""), assert_tests=assert_tests)

    if isinstance(first, (list, tuple)):
        deep_compare_ordered_collections(first, second, msg=(msg or ""), assert_tests=assert_tests)
    else:
        try:
            assert first == second, msg + f" :: {first=} != {second=}"
        except AssertionError:
            if assert_tests:
                raise
            return False

    return True


def compare_dataframes(
    df1: pd.DataFrame,
    df2: pd.DataFrame,
    cols: None | Iterable[str] = None,
    msg: None | str = None,
    ignore_col_order: bool = False,
    ignore_row_order: bool = True,
    ignore_index: bool = False,
    assert_tests: bool = True,
    **assert_frame_equal_kwargs,
) -> bool:
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
    returns - true if they are equivalent, false if not (if assert_tests is True then an inequality
        will result in an AssertionError instead of a returned False)
    """
    assert not (
        msg is not None and "obj" in assert_frame_equal_kwargs
    ), "'msg' and 'obj' keyword args cannot be used together"
    if not __debug__ and assert_tests is True:
        raise ValueError("assert_tests cannot be true in optimized/non debug mode")

    assert isinstance(df1, pd.DataFrame)
    assert isinstance(df2, pd.DataFrame)

    if cols is not None:
        # trim the result to the columns to test
        cols_as_set = set(cols) if not isinstance(cols, set) else cols
        assert (
            len(missing_cols := cols_as_set - set(df1.columns)) == 0
        ), f"Not all the requested cols are in df1. {missing_cols=}"
        assert (
            len(missing_cols := cols_as_set - set(df2.columns)) == 0
        ), f"Not all the requested cols are in df2. {missing_cols=}"
        df1 = df1[cols]
        df2 = df2[cols]

    if ignore_col_order is True:
        # sort both by column name
        df1 = df1[sorted(df1.columns)]
        df2 = df2[sorted(df2.columns)]

    # sort the dataframes
    if ignore_row_order is True:
        df1 = df1.sort_values(by=sorted(df1.columns))
        df2 = df2.sort_values(by=sorted(df2.columns))

    if ignore_index is True:
        df1 = df1.reset_index(drop=True)
        df2 = df2.reset_index(drop=True)

    try:
        if df1.columns.tolist() != df2.columns.tolist():
            prefix = (msg + " :: ") if msg is not None else ""
            assert set(df1.columns) == set(df2.columns), prefix + (
                "column names don't match. "
                f"{set(df1.columns) - set(df2.columns)} in df1 and not in df2. "
                f"{set(df2.columns) - set(df1.columns)} in df2 and not in df1"
            )
            assert not ignore_col_order, (
                f"{prefix}Not sure why, but the column names don't match. "
                "{df1.columns=} {df2.columns=}"
            )
            raise AssertionError(
                prefix + "The order of the columns does not match. {df1.columns=} {df2.columns=}"
            )

        kwargs = dict(assert_frame_equal_kwargs)
        if "check_names" not in kwargs:
            kwargs["check_names"] = True
        pd.testing.assert_frame_equal(
            df1, df2, obj=(msg + " dataframes") if msg is not None else None, **kwargs
        )
    except AssertionError:
        if assert_tests:
            raise
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
            assert hasattr(obj1, attr_name), f"{msg}: obj1 does not have attribute '{attr_name}'"
            assert hasattr(obj2, attr_name), f"{msg}: obj2 does not have attribute '{attr_name}'"

            deep_compare(
                getattr(obj1, attr_name),
                getattr(obj2, attr_name),
                assert_tests=True,
                msg=msg + f" >> obj1.{attr_name} != obj2.{attr_name}",
            )
    except AssertionError:
        if assert_tests:
            raise
        else:
            return False

    return True


def deep_compare_ordered_collections(objs1, objs2, msg="", assert_tests=True):
    """compare two iterable/ordered collections"""
    if not __debug__ and assert_tests is True:
        raise ValueError("assert_tests cannot be true in optimized/non debug mode")

    try:
        assert len(objs1) == len(objs2), (
            f"{msg}: lengths do not match. objs1 has length {len(objs1)}, "
            f"objs2 has length {len(objs2)}"
        )
        for i, (obj1, obj2) in enumerate(zip(objs1, objs2)):
            deep_compare(obj1, obj2, msg=msg + f": items {i} don't match")
    except AssertionError:
        if assert_tests:
            raise
        else:
            return False

    return True


def deep_compare_dicts(
    dict1, dict2, msg="", key_names=None, assert_tests=True, minimal_key_test=False
):
    """
    assert_tests: if true then comparison failures will raise assertion errors
    minimal_test: if true then only compare values for keys in key_names, or if key_names is None
       only compare values for keys in dict1. all other keys are ignored,
       if false then dicts must have the same set of keys

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
        if minimal_key_test:
            if key_names is None:
                key_names_set = set(dict1.keys())
            else:
                key_names_set = set(key_names)

            assert key_names_set <= set(dict1.keys()), (
                msg + f": dict1 does not have keys {key_names_set - set(dict1.keys())}"
            )
            assert key_names_set <= set(dict2.keys()), (
                msg + f": dict2 does not have keys {key_names_set - set(dict2.keys())}"
            )
        else:
            assert (d1_keys := set(dict1.keys())) == (d2_keys := set(dict2.keys())), (
                msg + ": dict keys don't match. "
                f"Keys in dict1 and missing from dict2 = {d1_keys - d2_keys}. "
                f"Keys in dict2 and missing from dict1 = {d2_keys - d1_keys}"
            )

        for key_name in key_names_set:
            assert key_name in dict1, msg + f": {key_name=} not in dict1"
            assert key_name in dict2, msg + f": {key_name=} not in dict2"
            deep_compare(
                dict1[key_name],
                dict2[key_name],
                assert_tests=True,
                msg=msg + "dict1['{key_name}'] != dict2['{key_name}']".format(key_name=key_name),
            )
    except AssertionError:
        if assert_tests:
            raise
        else:
            return False

    return True
