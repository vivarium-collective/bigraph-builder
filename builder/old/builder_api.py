"""
Bigraph Builder
================

API for building process bigraphs, integrating bigraph-schema, process-bigraph, and bigraph-viz under an intuitive
Python API.
"""

from process_bigraph import Process, Composite, process_registry, types
from bigraph_viz import plot_bigraph
import pprint

pretty = pprint.PrettyPrinter(indent=2)


def pf(x):
    return pretty.pformat(x)


class Builder(dict):

    def __init__(self, tree=None):
        super().__init__()
        self.tree = tree or {}  # TODO -- does this need to be a builder at every level?
        self.compiled_composite = None

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
        for key in keys:
            d = d[key]  # move deeper into the dictionary

        if d['_type'] in ['process', 'step', 'edge']:
            pass  # TODO -- look in the outputs of the process

        return d

    def __repr__(self):
        return f"{pf(self.tree)}"

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

    def connect(self, port_id, target_path):
        assert self['_type'] in ['process', 'step', 'edge']
        if port_id in self['inputs']:
            self['inputs'][port_id] = target_path
        if port_id in self['outputs']:
            self['outputs'][port_id] = target_path

        self.compiled_composite = None

    def document(self):
        return dict({'state': self.tree})

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



def build_gillespie():

    gillespie = Builder()
    gillespie['event_process'].add_process(type='event', protocol='local', rate_param=1.0, wires={})  # protocol local should be default. kwargs could fill the config
    gillespie['interval_process'].add_process(type='interval')

    print(gillespie['event_process'].ports())
    gillespie['event_process'].connect(port='DNA', target=['DNA_store'])
    gillespie['DNA_store'] = {'C': 2.0}  # this should check the type
    gillespie['event_process', 'DNA'].connect(['DNA_store'])  # TODO this should be an output from event_process
    gillespie['DNA_store'].connect(['event_process', 'DNA'])  # This is an input to event_process

    gillespie.compile()  # this fills and checks, this should also connect ports to stores with the same name, at the same level


    gillespie.plot()
    composite_data = gillespie.document()  # get the document
    gillespie.write(filename='gillespie1')  # save the document

    gillespie.run()

    results = gillespie.get_results()


if __name__ == '__main__':
    build_gillespie()
