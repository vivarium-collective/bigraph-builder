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

from process_bigraph import Process, Composite, process_registry, types
import process_bigraph.experiments.minimal_gillespie
from bigraph_viz import plot_bigraph


pretty = pprint.PrettyPrinter(indent=2)


def pf(x):
    return pretty.pformat(x)


EDGE_KEYS = ['process', 'step', 'edge']


def generate_builder_tree(tree):
    tree = tree or {}
    builder_tree = {}
    for k, i in tree.items():
        if isinstance(i, dict):
            builder_tree[k] = Builder(i)
        else:
            builder_tree[k] = i  # leaves
    return builder_tree


class Builder:

    def __init__(self, tree=None, schema=None):
        super().__init__()
        self.tree = generate_builder_tree(tree)
        self.schema = schema or {}  # TODO -- need to track schema
        self.compiled_composite = None

    def __repr__(self):
        return f"{pf(self.tree)}"

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
            self.tree[first_key] = value

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
            name='',
            protocol='local',
            config=None,
            inputs=None,
            outputs=None,
            **kwargs
    ):
        config = config or {}
        config.update(kwargs)
        edge_type = 'process'
        state = {
                # '_type': edge_type,
                'address': f'{protocol}:{name}',
                'config': config,
                'inputs': inputs or {},
                'outputs': outputs or {},
            }

        deserialized_state = types.deserialize(schema={'_type': edge_type}, encoded=state)

        self.tree = Builder(tree=deserialized_state)
        self.schema = deserialized_state['instance'].schema()
        self.schema['_type'] = edge_type

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
        return dict({
            'state': self.tree,
            'schema': self.schema})

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
        document = self.document()
        self.compiled_composite = Composite(document)
        return self.compiled_composite

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
        name='!process_bigraph.experiments.minimal_gillespie.GillespieEvent',
        protocol='local',
        rate_param=1.0,
        # inputs={},
        # outputs={},
    )  # protocol local should be default. kwargs could fill the config
    gillespie['interval_process'].add_process(name='!process_bigraph.experiments.minimal_gillespie.GillespieInterval')

    # print(gillespie['event_process'].ports())
    gillespie['event_process'].connect(target=['DNA_store'], port='DNA')
    gillespie['DNA_store'] = {'C': 2.0}  # this should check the type
    # gillespie['event_process', 'DNA'].connect(['DNA_store'])  # TODO this should be an output from event_process
    # gillespie['DNA_store'].connect(['event_process', 'DNA'])  # This is an input to event_process

    gillespie.compile()  # this fills and checks, this should also connect ports to stores with the same name, at the same level

    gillespie.plot()  # create bigraph plot
    composite_data = gillespie.document()  # get the document
    gillespie.write(filename='gillespie1')  # save the document
    gillespie.run(10)  # run simulation
    results = gillespie.get_results()

    # This needs to work
    node = gillespie['path', 'to']
    node.add_process()


if __name__ == '__main__':
    build_gillespie()
