from enum import Enum
from typing import Iterable

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
            assert first == second, f"{msg} :: {first=} != {second=}"
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
    try:
        if msg is not None and "obj" in assert_frame_equal_kwargs:
            raise ValueError("'msg' and 'obj' keyword args cannot be used together")
        if not __debug__ and assert_tests is True:
            raise ValueError("assert_tests cannot be true in optimized/non debug mode")

        assert isinstance(df1, pd.DataFrame)
        assert isinstance(df2, pd.DataFrame)

        if cols is not None:
            if not ignore_col_order:
                raise ValueError("Cannot specify cols and test col order")
            # trim the result to the columns to test
            cols_as_set = set(cols) if not isinstance(cols, set) else cols
            assert len(missing_cols := cols_as_set - set(df1.columns)) == 0, (
                f"Not all the requested cols are in df1. {missing_cols=}"
            )
            assert len(missing_cols := cols_as_set - set(df2.columns)) == 0, (
                f"Not all the requested cols are in df2. {missing_cols=}"
            )
            df1 = df1[cols]
            df2 = df2[cols]
        elif not ignore_col_order:
            assert list(df1.columns) == list(df2.columns), (
                "The order of the columns does not match. {df1.columns=} {df2.columns=}"
            )
        else:
            assert set(df1.columns) == set(df2.columns), (
                "column names don't match. "
                f"{set(df1.columns).difference(df2.columns)} in df1 and not in df2. "
                f"{set(df2.columns).difference(df1.columns)} in df2 and not in df1"
            )
            # sort both by column name
            df1 = df1[sorted(df1.columns)]
            df2 = df2[sorted(df2.columns)]

        if not ignore_index:
            assert (multi_index := isinstance(df1.index, pd.MultiIndex)) == isinstance(
                df2.index, pd.MultiIndex
            )
            if multi_index:
                assert df1.index.names == df2.index.names
            else:
                assert df1.index.name == df2.index.name

        if ignore_row_order is True:
            # sort the dataframes
            sort_by = sorted(df1.columns)
            if not ignore_index:
                if isinstance(df1.index, pd.MultiIndex):
                    sort_by = [*df1.index.names, *sort_by]
                else:
                    if df1.index.name is None:
                        df1.index.name = "INDEX"
                        df2.index.name = "INDEX"
                    sort_by.insert(0, df1.index.name)
            df1 = df1.sort_values(by=sort_by)
            df2 = df2.sort_values(by=sort_by)

        if ignore_index:
            df1 = df1.reset_index(drop=True)
            df2 = df2.reset_index(drop=True)

        kwargs = dict(assert_frame_equal_kwargs)
        if "check_names" not in kwargs:
            kwargs["check_names"] = True
        if msg is not None:
            kwargs["obj"] = msg + " dataframes"
        pd.testing.assert_frame_equal(df1, df2, **kwargs)
    except AssertionError as ex:
        if assert_tests:
            assert False, ex
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
        return False

    return True


def deep_compare_dicts(
    dict1: dict,
    dict2: dict,
    msg="",
    assert_tests=True,
    key_names: list[str] | None = None,
    minimal_key_test=False,
    ignore_keys: list[str] | None = None,
) -> bool:
    """
    assert_tests: if true then comparison failures will raise assertion errors
    minimal_test: if true then only compare values for keys in key_names, or\
        if key_names is None only compare values for keys in dict1. all other\
        keys are ignored, if false then dicts must have the same set of keys
    ignore_keys: only test keys NOT in this list, cannot be used with\
        minimal_key_test or key_names

    returns: true if the dicts match, false otherwise
    raises ValueError if testing is true and a mismatch is found
    """
    if not __debug__ and assert_tests is True:
        raise ValueError("assert_tests cannot be true in optimized/non debug mode")

    assert isinstance(dict1, dict), "dict1 should be a dict"
    assert isinstance(dict2, dict), "dict2 should be a dict"

    if msg is not None:
        msg += " :: "

    try:
        if minimal_key_test:
            if ignore_keys is not None:
                raise ValueError("ignore_keys cannot be used with minimal_key_test")
            if key_names is None:
                key_names_set = dict1.keys()
            else:
                key_names_set = set(key_names)

            assert key_names_set <= dict1.keys(), (
                msg + f": dict1 does not have keys {key_names_set - dict1.keys()}"
            )
            assert key_names_set <= dict2.keys(), (
                msg + f": dict2 does not have keys {key_names_set - dict2.keys()}"
            )
        elif key_names is not None:
            raise ValueError("If minimal_key_test is False key_names must be None")
        else:
            key_names_set = set(dict1.keys())
            d2_keys = set(dict2.keys())
            if ignore_keys:
                for key in ignore_keys:
                    key_names_set.discard(key)
                    d2_keys.discard(key)
            assert key_names_set == d2_keys, (
                msg + ": dict keys don't match. "
                f"Keys in dict1 and missing from dict2 = {key_names_set - d2_keys}. "
                f"Keys in dict2 and missing from dict1 = {d2_keys - key_names_set}"
            )

        mismatches = []
        for key_name in key_names_set:
            assert key_name in dict1, msg + f": {key_name=} not in dict1"
            assert key_name in dict2, msg + f": {key_name=} not in dict2"
            if not deep_compare(
                dict1[key_name],
                dict2[key_name],
                assert_tests=False,
            ):
                mismatches.append((key_name, dict1[key_name], dict2[key_name]))

        if mismatches:
            mismatch_details = "\n".join(
                [f"  {key}: dict1={val1!r}, dict2={val2!r}" for key, val1, val2 in mismatches]
            )
            raise AssertionError(
                f"{msg}{len(mismatches)} key(s) with mismatched values:\n{mismatch_details}"
            )
    except AssertionError:
        if assert_tests:
            raise
        return False

    return True
