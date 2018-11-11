import pandas
from collections import namedtuple


def deep_compare(first, second, msg=None):
    if type(first) == pandas.DataFrame:
        compare_dataframes(first, season, msg=msg)
    elif hasattr(first, '__dict__'):
        deep_compare_objs(first, second, msg=(msg or ""))
    elif hasattr(first, '_fields'):
        # must be a named tuple...
        deep_compare_objs(first, second, attr_names=first._fields, msg=(msg or ""))
    elif type(first) == dict:
        deep_compare_dicts(first, second, msg=(msg or ""))
    elif isinstance(first, (list, tuple)):
        deep_compare_ordered_collections(first, second, msg=(msg or ""))
    else:
        assert first == second, msg


def compare_dataframes(df1, df2, cols=None, msg=None):
    assert type(df1) == pandas.DataFrame
    assert type(df2) == pandas.DataFrame

    if cols is not None:
        # trim the result to the columns to test
        for col_name in df1.columns:
            if col_name not in cols:
                df1 = df1.drop(col_name, 1)

        for col_name in df2.columns:
            if col_name not in cols:
                df2 = df2.drop(col_name, 1)

    assert df1.columns.tolist() == df2.columns.tolist(), \
        ((msg + " :: ") if msg is not None else "") + "column names don't match"

    # sort the dataframes
    df1 = df1.reindex(sorted(df1.columns), axis=1)
    df2 = df2.reindex(sorted(df2.columns), axis=1)

    pandas.util.testing.assert_frame_equal(df1, df2, check_names=True, obj=msg)


def deep_compare_objs(obj1, obj2, attr_names=None, msg=""):
    """
    if attr_names is not provided, then obj1 must implement __dict__ and return
    a list of attributes via the vars() built-in function
    """
    if attr_names is None:
        attr_names = vars(obj1)

    for attr_name in attr_names:
        assert hasattr(obj1, attr_name), \
            msg + ": obj1 does not have attribute '{}'".format(attr_name)
        assert hasattr(obj2, attr_name), \
            msg + ": obj2 does not have attribute '{}'".format(attr_name)
        deep_compare(getattr(obj1, attr_name),
                     getattr(obj2, attr_name),
                     msg + " >> obj1.{attr_name} != obj2.{attr_name}".format(attr_name=attr_name))


def deep_compare_ordered_collections(objs1, objs2, attr_names, msg=""):
    self.assertEqual(len(objs1), len(objs2),
                     msg +
                     ": lengths do not match. objs1 has length {}, objs2 has length {}".format(
                         len(objs1), len(objs2)))
    for i, (obj1, obj2) in enumerate(zip(objs1, objs2)):
        deep_compare(obj1, obj2, attr_names, msg + ": items {} don't match".format(i))


def deep_compare_dicts(dict1, dict2, msg="", key_names=None):
    assert isinstance(dict1, dict)
    assert isinstance(dict2, dict)

    if msg is not None:
        msg += " :: "

    if key_names is None:
        assert set(dict1.keys()) == set(dict2.keys())
        key_names = dict1.keys()
    else:
        key_names_set = set(key_names)
        assert key_names_set == set(dict1.keys()), msg + ": dict1 does not have key {}".format(key_name)
        assert key_names_set == set(dict2.keys()), msg + ": dict2 does not have key {}".format(key_name)

    for key_name in key_names:
        deep_compare(
            dict1[key_name], dict2[key_name],
            msg + "dict1['{key_name}'] != dict2['{key_name}']".format(key_name=key_name))