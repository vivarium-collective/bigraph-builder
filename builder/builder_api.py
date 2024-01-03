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

from process_bigraph import Process, Composite, process_registry, types, register_process
from process_bigraph.experiments.minimal_gillespie import GillespieEvent, GillespieInterval
from bigraph_viz import plot_bigraph


pretty = pprint.PrettyPrinter(indent=2)


def pf(x):
    return pretty.pformat(x)


EDGE_KEYS = ['process', 'step', 'edge']

# register processes
process_registry.register('GillespieEvent', GillespieEvent)
process_registry.register('GillespieInterval', GillespieInterval)


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


class Builder:

    def __init__(self, tree=None, schema=None):
        super().__init__()
        self.tree = builder_tree_from_dict(tree)
        self.schema = schema or {}  # TODO -- need to track schema
        self.compiled_composite = None

    def __repr__(self):
        return f"Builder:{pf(self.tree)}"

    def __setitem__(self, keys, value):
        # Convert single key to tuple
        keys = (keys,) if isinstance(keys, (str, int)) else keys

        first_key = keys[0]
        if first_key not in self.tree:
            self.tree[first_key] = Builder()

        remaining = keys[1:]
        if len(remaining) > 0:
            self.tree[first_key].__setitem__(remaining, value)
        else:
            self.tree[first_key] = Builder(tree=value)

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

        #     # TODO: reach through a port
        #     if i < len(keys) - 1 and d.get('_type') in EDGE_KEYS:
        #         # The current item is a process, and there's another key after this
        #         next_key = keys[i + 1]
        #         # Check if next_key is a valid port
        #         if 'ports' not in d or next_key not in d['ports']:
        #             raise ValueError(f"Port '{next_key}' not found in process '{key}'.")
        #     d = d[key]
        #
        # return d

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
            if not process_registry.access(name):
                assert process, f"Process '{name}' not found in registry, and no process provided."
                process_registry.register(name, process)

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
        self.compiled_composite = None

    def ports(self):
        if self.tree['_type'] not in EDGE_KEYS:
            warnings.warn(f"Expected '_type' to be in {EDGE_KEYS}, found '{self.tree['_type']}' instead.",
                          RuntimeWarning)

        if not self.compiled_composite:
            self.compile()
            # warnings.warn("ports requires compile", RuntimeWarning)

        # TODO get the ports

    def connect(self, port=None, target=None):
        assert self.schema['_type'] in EDGE_KEYS, f"Invalid type for connect: {self.schema}, needs to be in {EDGE_KEYS}"

        if port in self.schema['inputs']:
            self.tree['inputs'][port] = target
        if port in self.schema['outputs']:
            self.tree['outputs'][port] = target

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

    def plot(self, filename='bigraph', out_dir='out', **kwargs):
        return plot_bigraph(
            self.tree,
            out_dir=out_dir,
            filename=filename,
            **kwargs)

    def get_results(self, query=None):
        return self.compiled_composite.gather_results(query)


def build_gillespie():

    gillespie = Builder()
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
    gillespie['DNA_store'] = {'C': 2.0}  # TODO this should check the type
    gillespie['mRNA_store'] = {'C': 0.0}
    gillespie.compile()  # this fills and checks, this should also connect ports to stores with the same name, at the same level

    gillespie.plot()  # create bigraph plot
    doc = gillespie.document()  # get the document
    gillespie.write(filename='gillespie1')  # save the document
    gillespie.run(10)  # run simulation
    results = gillespie.get_results()

    # This needs to work
    node = gillespie['path', 'to']
    # node.add_process()


def test_builder():
    # make a process
    @register_process('toy')
    class Toy(Process):
        config_schema = {
            'A': {'_default': 1.0},
            'B': {'_default': 2.0},
        }

        def __init__(self, config):
            super().__init__(config)

        def schema(self):
            return {
                'inputs': {
                    'A': 'float',
                    'B': 'float'},
                'outputs': {
                    'C': 'float'}
            }

        def update(self, state, interval):
            update = {
                'C': state['A'] + state['B']
            }
            return update


if __name__ == '__main__':
    build_gillespie()
