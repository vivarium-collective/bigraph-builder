from process_bigraph import Composite
from bigraph_schema.registry import type_schema_keys
from api import pf


class Node:
    def __init__(self, data, schema_keys):
        self._data = data
        self._schema_keys = schema_keys

    def __getattr__(self, item):
        # Special handling for schema keys
        schema_key = f'_{item}'
        if schema_key in self._schema_keys:
            return self._data.get(schema_key)
        raise AttributeError(f"{item} is not a valid attribute or schema key.")

    def __setattr__(self, key, value):
        if key in ['_data', '_schema_keys']:
            super().__setattr__(key, value)
        else:
            schema_key = f'_{key}'
            if schema_key in self._schema_keys:
                self._data[schema_key] = value
            else:
                raise AttributeError(f"{key} is not a valid attribute or schema key.")

    def __repr__(self):
        return pf(self._data)


class Builder:
    def __init__(self, schema_keys=None, tree_dict=None):
        self._schema_keys = type_schema_keys
        if schema_keys:
            self._schema_keys.update(f'_{key}' for key in schema_keys)
        self.tree_dict = tree_dict if tree_dict is not None else {}

    def __getitem__(self, keys):
        if not isinstance(keys, tuple):
            keys = (keys,)

        current_dict = self.tree_dict
        for key in keys:
            current_dict = current_dict.setdefault(key, {})

        return Node(current_dict, self._schema_keys)

    def __setitem__(self, keys, value):
        if not isinstance(keys, tuple):
            keys = (keys,)

        current_dict = self.tree_dict
        for key in keys[:-1]:
            current_dict = current_dict.setdefault(key, {})

        # Assign the value to the '_value' key
        current_dict[keys[-1]] = {'_value': value}

    def __repr__(self):
        return pf(self.tree_dict)


def test_tree():

    # Example usage:
    tree = Builder(schema_keys=['apply', 'parameters'])

    # add a branch with a value
    tree['a', 'b'] = 2.0
    tree['a', 'b2', 'c'] = 12.0

    # access and print the 'apply' attribute
    print(tree['a', 'b'].apply)  # Output: None
    tree['a', 'b'].apply = 'sum'
    print(tree['a', 'b'].apply)  # Output: 'sum'
    print(tree['a', 'b'].value)  # Output: 2.0


    # test with preloaded dict
    tree2 = Builder(tree_dict={'path': {'to': {'leaf': {'_value': 1.0}}}}, schema_keys=['apply', 'parameters'])

    x=0




if __name__ == '__main__':
    test_tree()
