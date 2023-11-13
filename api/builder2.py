"""
Vivarium Builder
================

API for building process bigraphs, integrating bigraph-schema, process-bigraph, and bigraph-viz under an intuitive
Python API.
"""

from bigraph_schema.type_system import TypeSystem
from process_bigraph.composite import Composite
import pprint

pretty = pprint.PrettyPrinter(indent=2)


def pf(x):
    return pretty.pformat(x)


class Node(dict):
    def add_process(
            self,
            process_id,
            process_type=None,
            address=None,
            config=None,
            inputs=None,
            outputs=None,
    ):
        self[process_id] = {
            '_type': process_type or 'process',
            'address': address or '',
            'config': config or {},
            'wires': {
                'inputs': inputs or {},
                'outputs': outputs or {},
            },
        }


class Builder(Node):

    def __init__(self, tree_dict=None):
        super().__init__()
        self.tree_dict = tree_dict or {}
        self.processes = {}  # TODO retrieve this from tree_dict?

    def __setitem__(self, keys, value):
        # Convert single key to tuple
        keys = (keys,) if isinstance(keys, str) else keys

        # Navigate through the keys, creating nested dictionaries as needed
        d = self.tree_dict
        for key in keys[:-1]:  # iterate over keys to create the nested structure
            if key not in d:
                d[key] = Node()
            d = d[key]
        d[keys[-1]] = value  # set the value at the final level

    def __getitem__(self, keys):
        # Convert single key to tuple
        keys = (keys,) if isinstance(keys, str) else keys

        d = self.tree_dict
        for key in keys:
            d = d[key]  # move deeper into the dictionary
        return d

    def __repr__(self):
        return f"{pf(self.tree_dict)}"

    def make_composite(self):
        return Composite({'state': self.tree_dict})


def test_builder():
    # Testing the Builder class
    b = Builder()
    b['path', 'to', 'node'] = 1.0
    print(b.tree_dict)

    # Accessing the value
    value = b['path', 'to', 'node']
    print(value)

    b['path', 'b2', 'c'] = 12.0
    print(b)

    b.add_process(process_id='process1')
    b['path', 'to'].add_process(process_id='p1', process_type='example_type')
    print(b['path'])


    # print(b.state)  # this should be the state hierarchy
    print(b.processes)  # This should be the process registry
    print(b['path', 'b2', 'c'].type)  # access schema keys

    b['path', 'to', 'p1'].connect(port_id='', target=['path', '1'])  # connect port, with checking

    b.check()  # check if everything is connected
    b.infer()  # fill in missing content
    b.graph()  # bigraph-viz




def test_builder_demo():

    sed_schema = {
        'models': {},
        'algorithms': {},
        'visualizations': {},
        'tasks': {},
    }
    a = Builder(sed_schema)

    # or
    b = Builder()
    b['models'] = {}
    b['algorithms'] = {}
    b['visualizations'] = {}
    b['tasks'] = {}

    b.add_process(process_id='p1', address='', config={}, inputs={}, outputs={})





if __name__ == '__main__':
    # test_builder()
    test_builder_demo()
