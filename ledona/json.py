import numbers
import collections
import types
import datetime


def make_json_compatible(obj_):
    """
    take an object and make it into a json compatible object python objecy
    """
    if isinstance(obj_, (numbers.Number, str, bool)) or obj_ is None:
        # these are handled as is
        return obj_
    elif isinstance(obj_, collections.Mapping):
        return {
            make_json_compatible(k): make_json_compatible(v)
            for k, v in obj_.items()
        }
    elif isinstance(obj_, (collections.Iterable, collections.Set)):
        return [make_json_compatible(v) for v in obj_]
    elif isinstance(obj_, (datetime.datetime, datetime.date)):
        return obj_.isoformat()

    raise NotImplementedError("Dont know how to handle objects of type {}".format(type(obj_)))
