import unittest
from unittest.mock import MagicMock
import pandas


# TODO: somehow merge this with deep_compare
class BaseTestClass(unittest.TestCase):
    """Add some additional testing and assertions to the base test case class"""

    def assertDataFrameEqual(self, df1, df2, cols=None, msg=None):
        """
        Test for equivalence of 2 pandas data frames, ignoring column order
        cols is an optional set of column names. If it is set then only these columns will be
        considered during the assertion.
        """
        if cols is not None:
            # trim the result to the columns to test
            for col_name in df1.columns:
                if col_name not in cols:
                    df1 = df1.drop(col_name, 1)

            for col_name in df2.columns:
                if col_name not in cols:
                    df2 = df2.drop(col_name, 1)

        df1 = df1.reindex(sorted(df1.columns, key=str), axis=1)
        df2 = df2.reindex(sorted(df2.columns, key=str), axis=1)

        if cols is None:
            # test if the columns match
            self.assertEqual(
                df1.columns.tolist(),
                df2.columns.tolist(),
                ((msg + " :: ") if msg is not None else "")
                + "column names don't match",
            )
        pandas.testing.assert_frame_equal(df1, df2, check_names=True, obj=msg)

    def compare_obj_obj(self, obj1, obj2, attr_names, msg=""):
        """test that the values for attr_names attributes are the same across obj1 and obj2"""
        for attr_name in attr_names:
            self.assertTrue(
                hasattr(obj1, attr_name),
                msg + f": obj1 does not have attribute '{attr_name}'",
            )
            self.assertTrue(
                hasattr(obj2, attr_name),
                msg + f": obj2 does not have attribute '{attr_name}'",
            )
            self.assertEqual(
                getattr(obj1, attr_name),
                getattr(obj2, attr_name),
                msg
                + " >> obj1.{attr_name} != obj2.{attr_name}".format(
                    attr_name=attr_name
                ),
            )

    def compare_objs_objs(self, objs1, objs2, attr_names, msg=""):
        """use compare_obj_obj on list/tuple of objects"""
        self.assertEqual(
            len(objs1),
            len(objs2),
            msg + f": lengths do not match. {len(objs1)=}, {len(objs2)=}",
        )
        for i, (obj1, obj2) in enumerate(zip(objs1, objs2)):
            self.compare_obj_obj(
                obj1, obj2, attr_names, msg + f": items {i} don't match"
            )

    def assertEqual(self, first, second, msg=None):
        """
        convenience method that will call the data frame equality test if first and
        second are data fromes
        """
        if isinstance(first, pandas.DataFrame) and isinstance(second, pandas.DataFrame):
            return self.assertDataFrameEqual(first, second, msg=msg)

        if isinstance(first, pandas.Series) and isinstance(second, pandas.Series):
            return pandas.testing.assert_series_equal(first, second, obj=msg)

        if isinstance(first, MagicMock):
            return self.compare_obj_obj(first, second, first.keys(), msg=(msg or ""))

        if isinstance(first, dict) and isinstance(second, dict):
            self.assertEqual(set(first.keys()), set(second.keys()), msg)
            return self.compare_dict_dict(first, second, msg=(msg or ""))

        return super().assertEqual(first, second, msg)

    def compare_dict_dict(self, dict1, dict2, msg="", key_names=None):
        """
        test that the values for key_names are the same across dict1 and dict2
        dict1 - reference dict, if key_names is None, then only compare keys that are present in
          this dict
        key_names - if none then use all keys found in dict1, otherwise only compare
          these key_names
        """
        if msg is not None:
            msg += " :: "
        for key_name in key_names or dict1.keys():
            self.assertIn(
                key_name, dict1, msg + f": dict1 does not have key '{key_name}'"
            )
            self.assertIn(
                key_name, dict2, msg + f": dict2 does not have key '{key_name}'"
            )
            self.assertEqual(
                dict1[key_name],
                dict2[key_name],
                msg
                + "dict1['{key_name}'] != dict2['{key_name}']".format(
                    key_name=key_name
                ),
            )
