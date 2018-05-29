import argparse


class AttributeObject(argparse.Namespace):
    """
    an object that can be handled as a dict with key values, or an object with attributes
    useful for testing or as the base of classes that are mostly a bundle of attributes

    supports most dict operations and methods (e.g. dict.items(), dict.keys(), dict.values(), etc...)
    and object operations (e.g. obj.ATTR, obj.ATTR = BLAH)
    """
    def __getitem__(self, key):
        return getattr(self, key)

    def __setitem__(self, key, value):
        setattr(self, key, value)

    def __hash__(self):
        raise NotImplementedError()
        return hash(flatten_dict_to_frozensets(vars(self)))

    def __len__(self):
        return len(vars(self))

    def get(self, key, default):
        return getattr(self, key, default)

    def items(self):
        return vars(self).items()

    def keys(self):
        return vars(self).keys()

    def values(self):
        return vars(self).values()
