"""
Bigraph Builder
================

API for building process bigraphs, integrating bigraph-schema, process-bigraph, and bigraph-viz under an intuitive
Python API.
"""
import os
import json
import pprint
import warnings

from process_bigraph import Process, Composite, types, register_process
from process_bigraph import process_registry as PROCESS_REGISTRY
from process_bigraph.experiments.minimal_gillespie import GillespieEvent, GillespieInterval
from bigraph_viz import plot_bigraph


pretty = pprint.PrettyPrinter(indent=2)


def pf(x):
    return pretty.pformat(x)


EDGE_KEYS = ['process', 'step', 'edge']


def builder_tree_from_dict(d):
    d = d or {}
    builder_tree = {}
    for k, i in d.items():
        if isinstance(i, dict):
            builder_tree[k] = Builder(i)
        else:
            builder_tree[k] = i  # leaves
    return builder_tree


def dict_from_builder_tree(builder_tree):
    tree = {}
    for k, i in builder_tree.items():
        if isinstance(i, Builder):
            tree[k] = dict_from_builder_tree(i.tree)
        else:
            tree[k] = i  # leaves
    return tree


def get_process_ports(value, schema):
    ports = {}
    if value.get('_type') in EDGE_KEYS:
        ports['_inputs'] = schema.get('_inputs', {})
        ports['_outputs'] = schema.get('_outputs', {})
    return ports


def fill_process_ports(tree, schema):
    new_tree = tree.copy()
    for key, value in tree.items():
        if value.get('_type') in EDGE_KEYS:
            if '_ports' not in new_tree[key]:
                new_tree[key]['_ports'] = {}
            new_tree[key]['_ports'].update(schema[key].get('_inputs', {}))
            new_tree[key]['_ports'].update(schema[key].get('_outputs', {}))
        elif isinstance(value, dict) and key in schema:
            new_tree[key] = fill_process_ports(value, schema[key])
    return new_tree


class Builder:

    def __init__(self, tree=None, schema=None, process_registry=None):
        super().__init__()
        self.tree = builder_tree_from_dict(tree)
        self.schema = schema or {}  # TODO -- need to track schema
        self.compiled_composite = None
        self.process_registry = process_registry or PROCESS_REGISTRY

    def __repr__(self):
        return f"Builder({pf(self.tree)})"

    def __setitem__(self, keys, value):
        # Convert single key to tuple
        keys = (keys,) if isinstance(keys, (str, int)) else keys

        first_key = keys[0]
        if first_key not in self.tree:
            self.tree[first_key] = Builder()

        remaining = keys[1:]
        if len(remaining) > 0:
            self.tree[first_key].__setitem__(remaining, value)
        elif isinstance(value, dict):
            self.tree[first_key] = Builder(tree=value)
        else:
            self.tree[first_key] = value

        # reset compiled composite
        self.compiled_composite = None

    def __getitem__(self, keys):
        # Convert single key to tuple
        keys = (keys,) if isinstance(keys, (str, int)) else keys

        first_key = keys[0]
        if first_key not in self.tree:
            self.tree[first_key] = Builder()

        remaining = keys[1:]
        if len(remaining) > 0:
            return self.tree[first_key].__getitem__(remaining)
        else:
            return self.tree[first_key]

    def process_registry_list(self):
        return self.process_registry.list()

    def register_process(self, name, process, force=False):
        self.process_registry.register(name, process, force=force)

    def add_process(
            self,
            name=None,
            protocol='local',
            process=None,
            config=None,
            inputs=None,
            outputs=None,
            **kwargs
    ):
        config = config or {}
        config.update(kwargs)
        edge_type = 'process'

        # register processes
        if protocol == 'local':
            if not self.process_registry.access(name):
                assert process, f"Process '{name}' not found in registry, and no process provided."
                self.process_registry.register(name, process)

        # get the address
        address = None
        if protocol == 'path':
            address = f'local:!{name}'
        else:
            address = f'{protocol}:{name}'

        # make the schema
        initial_state = {
                '_type': edge_type,
                'address': address,
                'config': config,
                'inputs': inputs or {},
                'outputs': outputs or {},
            }

        initial_schema = {'_type': edge_type}
        schema, state = types.complete(initial_schema, initial_state)

        self.tree = builder_tree_from_dict(state)
        self.schema = schema

        # reset compiled composite
        self.compiled_composite = None

    def connect(self, port=None, target=None):
        assert self.schema.get('_type') in EDGE_KEYS, f"Invalid type for connect: {self.schema}, needs to be in {EDGE_KEYS}"

        if port in self.schema['_inputs']:
            self.tree['inputs'][port] = target
        if port in self.schema['_outputs']:
            self.tree['outputs'][port] = target

        # reset compiled composite
        self.compiled_composite = None

    def document(self):
        doc = types.serialize(
            self.schema,
            dict_from_builder_tree(self.tree))
        return doc

    def write(self, filename, outdir='out'):
        if not os.path.exists(outdir):
            os.makedirs(outdir)

        filepath = f"{outdir}/{filename}.json"
        document = self.document()

        # Writing the dictionary to a JSON file
        with open(filepath, 'w') as json_file:
            json.dump(document, json_file, indent=4)

        print(f"File '{filename}' successfully written in '{outdir}' directory.")

    def compile(self):
        self.schema, tree = types.complete(
            self.schema,
            dict_from_builder_tree(self.tree)
        )
        self.tree = builder_tree_from_dict(tree)
        self.compiled_composite = Composite({'state': tree, 'composition': self.schema})

    def run(self, interval):
        if not self.compiled_composite:
            self.compile()
        self.compiled_composite.run(interval)

    def ports(self):
        self.compile()
        tree_dict = dict_from_builder_tree(self.tree)
        tree_type = tree_dict.get('_type')
        if not tree_type:
            warnings.warn(f"no type provided.")
        elif tree_type not in EDGE_KEYS:
            warnings.warn(f"Expected '_type' to be in {EDGE_KEYS}, found '{tree_type}' instead.")
        elif tree_type:
            return get_process_ports(tree_dict, self.schema)

    def plot(self, filename=None, out_dir=None, **kwargs):
        if filename and not out_dir:
            out_dir = 'out'
        if not self.compiled_composite:
            self.compile()

        tree_dict = dict_from_builder_tree(self.tree)
        tree_dict = fill_process_ports(tree_dict, self.schema)

        return plot_bigraph(
            tree_dict,
            out_dir=out_dir,
            filename=filename,
            show_process_schema=False,
            **kwargs)

    def get_results(self, query=None):
        return self.compiled_composite.gather_results(query)


def build_gillespie():
    # register processes
    PROCESS_REGISTRY.register('GillespieEvent', GillespieEvent)
    PROCESS_REGISTRY.register('GillespieInterval', GillespieInterval)

    gillespie = Builder(process_registry=PROCESS_REGISTRY)
    gillespie['event_process'].add_process(
        name='GillespieEvent',
        kdeg=1.0,  # kwargs fill parameters in the config

    )
    gillespie['interval_process'].add_process(
        name='process_bigraph.experiments.minimal_gillespie.GillespieInterval',
        protocol='path',
    )

    # print(gillespie['event_process'].ports())
    # TODO -- ports should connect more automatically and check types
    gillespie['event_process'].connect(port='DNA', target=['DNA_store'])
    gillespie['event_process'].connect(port='mRNA', target=['mRNA_store'])
    gillespie['interval_process'].connect(port='DNA', target=['DNA_store'])
    gillespie['interval_process'].connect(port='mRNA', target=['mRNA_store'])
    gillespie['DNA_store'] = {'C': 2.0, 'G': 1.0}  # TODO this should check the type
    gillespie['mRNA_store'] = {'C': 0.0, 'G': 0.0}
    gillespie.compile()  # this fills and checks, this should also connect ports to stores with the same name, at the same level

    gillespie.plot(filename='gillespie_bigraph')  # create bigraph plot
    doc = gillespie.document()  # get the document
    gillespie.write(filename='gillespie1')  # save the document
    gillespie.run(10)  # run simulation
    results = gillespie.get_results()

    # This needs to work
    node = gillespie['path', 'to']
    # node.add_process()


def test1():
    b = Builder()

    class Toy(Process):
        config_schema = {
            'A': 'float',
            'B': 'float'}
        def __init__(self, config):
            super().__init__(config)
        def schema(self):
            return {
                'inputs': {
                    'A': 'float',
                    'B': 'float'},
                'outputs': {
                    'C': 'float'}}
        def update(self, state, interval):
            return {'C': state['A'] + state['B']}

    b.register_process('toy', Toy)
    print(b.process_registry_list())

    b['toy'].add_process(name='toy')

    # b.tree
    ports = b['toy'].ports()
    print(ports)

    b.compile()
    ports = b['toy'].ports()
    print(ports)

    b.plot()


if __name__ == '__main__':
    # build_gillespie()
    test1()
