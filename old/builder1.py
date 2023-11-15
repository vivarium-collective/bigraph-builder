from process_bigraph import Composite
from bigraph_schema.registry import type_schema_keys
from builder import pf
import json
import os
import uuid


def make_process_config(
        type=None,
        address=None,
        config=None,
        wires=None
):
    return {
        '_type': type,
        'address': address,
        'config': config,
        'wires': wires or {},
    }


class Node:
    """
    Provides attribute-style access to the data within a tree
    """

    def __init__(self, data, schema_keys, path, builder):
        self._data = data
        self._schema_keys = schema_keys
        self._path = path  # the current path
        self._builder = builder  # the builder instance

    def __getattr__(self, item):
        schema_key = f'_{item}'
        if schema_key in self._schema_keys:
            return self._data.get(schema_key)
        raise AttributeError(f"{item} is not a valid attribute or schema key.")

    def __setattr__(self, key, value):
        if key in ['_data', '_schema_keys', '_path', '_builder']:
            super().__setattr__(key, value)
        else:
            schema_key = f'_{key}'
            if schema_key in self._schema_keys:
                self._data[schema_key] = value
            else:
                raise AttributeError(f"{key} is not a valid attribute or schema key.")

    def __repr__(self):
        return f"Node({self._data})"

    def add_process(
            self,
            process_id,
            type=None,
            address=None,
            config=None,
            wires=None
    ):
        # Add the process with the given ID and attributes
        self._data[process_id] = make_process_config(type, address, config, wires)

        # Update the builder's tree_dict
        self._builder.update_tree(self._path, self._data)


class Builder:
    schema_keys = {'_value'}

    def __init__(self, schema_keys=None, bigraph_dict=None):
        if schema_keys:
            self.schema_keys.update(f'_{key}' for key in schema_keys if not key.startswith('_'))
        self._bigraph = bigraph_dict or {}

    def __repr__(self):
        return f"{self._bigraph}"

    def __getitem__(self, keys):
        if not isinstance(keys, tuple):
            keys = (keys,)

        current_dict = self._bigraph
        for key in keys:
            current_dict = current_dict.setdefault(key, {})

        return Node(current_dict, self.schema_keys, keys, self)

    def __setitem__(self, keys, value):
        if not isinstance(keys, tuple):
            keys = (keys,)

        current_dict = self._bigraph
        for key in keys[:-1]:
            current_dict = current_dict.setdefault(key, {})

        # Assign the value to the '_value' key
        current_dict[keys[-1]] = {'_value': value}

    def add_process(
            self,
            process_id,
            type=None,
            address=None,
            config=None,
            wires=None
    ):
        # Add the process with the given ID and attributes
        self._bigraph[process_id] = make_process_config(type, address, config, wires)

    def update_tree(self, path, data):
        # Navigate to the correct location in the tree and update the data
        current_dict = self._bigraph
        for key in path[:-1]:
            current_dict = current_dict.setdefault(key, {})
        current_dict[path[-1]] = data



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

    tree2




if __name__ == '__main__':
    test_tree()
