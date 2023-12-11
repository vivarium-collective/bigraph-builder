"""
Bigraph Builder
================

API for building process bigraphs, integrating bigraph-schema, process-bigraph, and bigraph-viz under an intuitive
Python API.
"""
import json
import pprint
import warnings

from process_bigraph import Process, Composite, process_registry, types
from bigraph_viz import plot_bigraph


pretty = pprint.PrettyPrinter(indent=2)


def pf(x):
    return pretty.pformat(x)

EDGE_KEYS = ['process', 'step', 'edge']


class Builder(dict):

    def __init__(self, tree=None):
        super().__init__()
        self.tree = tree or {}  # TODO -- does this need to be a builder at every level?
        self.compiled_composite = None

    def __repr__(self):
        return f"{pf(self.tree)}"

    def __setitem__(self, keys, value):
        # Convert single key to tuple
        keys = (keys,) if isinstance(keys, str) else keys

        # Navigate through the keys, creating nested dictionaries as needed
        d = self.tree
        for key in keys[:-1]:  # iterate over keys to create the nested structure
            if key not in d:
                d[key] = Builder()
            d = d[key]
        d[keys[-1]] = value  # set the value at the final level

        self.compiled_composite = None

    def __getitem__(self, keys):
        # Convert single key to tuple
        keys = (keys,) if isinstance(keys, str) else keys

        d = self.tree
        for i, key in enumerate(keys):
            if key not in d:
                d[key] = Builder()

            # TODO: reach through a port
            if i < len(keys) - 1 and d.get('_type') in EDGE_KEYS:
                # The current item is a process, and there's another key after this
                next_key = keys[i + 1]
                # Check if next_key is a valid port
                if 'ports' not in d or next_key not in d['ports']:
                    raise ValueError(f"Port '{next_key}' not found in process '{key}'.")

            d = d[key]

        return d

    def add_process(
            self,
            name='process',
            protocol='local',
            config=None,
            inputs=None,
            outputs=None,
            **kwargs
    ):
        config = config or {}
        config.update(kwargs)
        self.tree = {
            '_type': 'process',
            'address': f'{protocol}:{name}',
            'config': config,
            'inputs': inputs or {},
            'outputs': outputs or {},
        }

        self.compiled_composite = None

    def ports(self):
        if self.tree['_type'] not in EDGE_KEYS:
            warnings.warn(f"Expected '_type' to be in {EDGE_KEYS}, found '{self.tree['_type']}' instead.",
                          RuntimeWarning)

        if not self.compiled_composite:
            warnings.warn("ports requires compile", RuntimeWarning)

    def connect(self, target, port=None):
        assert self.tree['_type'] in EDGE_KEYS, f"Invalid type for connect: {self.tree}, needs to be in {EDGE_KEYS}"
        if port in self.tree['inputs']:
            self.tree['inputs'][port] = target
        if port in self.tree['outputs']:
            self.tree['outputs'][port] = target

        self.compiled_composite = None

    def document(self):
        return dict({'state': self.tree})

    def write(self, filename, outdir='out'):
        filepath = f"{outdir}/{filename}"
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

    def plot(self, **kwargs):
        return plot_bigraph(self.tree, **kwargs)

    def get_results(self, query=None):
        return self.compiled_composite.gather_results(query)


def build_gillespie():

    gillespie = Builder()
    gillespie['event_process'].add_process(type='event', protocol='local', rate_param=1.0, wires={})  # protocol local should be default. kwargs could fill the config
    gillespie['interval_process'].add_process(type='interval')

    print(gillespie['event_process'].ports())
    gillespie['event_process'].connect(target=['DNA_store'], port='DNA')
    gillespie['DNA_store'] = {'C': 2.0}  # this should check the type
    gillespie['event_process', 'DNA'].connect(['DNA_store'])  # TODO this should be an output from event_process
    gillespie['DNA_store'].connect(['event_process', 'DNA'])  # This is an input to event_process

    gillespie.compile()  # this fills and checks, this should also connect ports to stores with the same name, at the same level

    gillespie.plot()  # create bigraph plot
    composite_data = gillespie.document()  # get the document
    gillespie.write(filename='gillespie1')  # save the document
    gillespie.run()  # run simulation
    results = gillespie.get_results()


if __name__ == '__main__':
    build_gillespie()
