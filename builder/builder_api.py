"""
Bigraph Builder
================

API for building process bigraphs, integrating bigraph-schema, process-bigraph, and bigraph-viz under an intuitive
Python API.
"""
import os
import inspect
import json
from pprint import pformat as pf
import warnings

from process_bigraph import Process, Step, Composite, ProcessTypes
from bigraph_schema.protocols import local_lookup_module
from bigraph_viz import plot_bigraph


EDGE_KEYS = ['process', 'step', 'edge']  # todo -- replace this with core.check() or similar


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
        if isinstance(value, dict):
            if value.get('_type') in EDGE_KEYS:
                if '_ports' not in new_tree[key]:
                    new_tree[key]['_ports'] = {}
                input_ports = schema[key].get('_inputs', {})
                output_ports = schema[key].get('_outputs', {})

                for port, v in input_ports.items():
                    if port not in new_tree[key]['inputs']:
                        new_tree[key]['_ports'][port] = v
                for port, v in output_ports.items():
                    if port not in new_tree[key]['outputs']:
                        new_tree[key]['_ports'][port] = v

            elif key in schema:
                new_tree[key] = fill_process_ports(value, schema[key])

    return new_tree


class Builder:

    def __init__(self, tree=None, schema=None, parent=None, core=None):
        super().__init__()
        self.tree = builder_tree_from_dict(tree)
        self.schema = schema or {}  # TODO -- need to track schema
        self.core = core or ProcessTypes()
        self.parent = parent

        self.compiled_composite = None

        # TODO -- add an emitter by default so results are automatic

    def register_process(self, process_name, address):
        assert isinstance(process_name, str), f'process name must be a string: {process_name}'
        # Check if address is a class object
        if inspect.isclass(address):
            self.core.process_registry.register(process_name, address)
        # Check if address is a string
        elif isinstance(address, str):
            try:
                # separate out the protocol from the address
                protocol, addr = address.split(':', 1)
                assert protocol == 'local', 'BigraphBuilder only supports local protocol in the current version'

                # TODO -- check protocol registry?
                if addr[0] == '!':
                    process_class = local_lookup_module(addr[1:])
                    # Now you have the protocol and address separated, you can process them as needed
                    self.core.process_registry.register(process_name, process_class)
                else:
                    Exception('only support local addresses')

            except ValueError:
                Exception(f"Address '{address}' does not contain a protocol. Registration failed.")
        else:
            # Handle other types if necessary
            Exception(f"Unsupported address type for {process_name}. Registration failed.")

    def top(self):
        # recursively get the top parent
        if self.parent:
            return self.parent.top()
        else:
            return self

    def __repr__(self):
        return f"Builder({pf(self.tree)})"

    def __setitem__(self, keys, value):
        # Convert single key to tuple
        keys = (keys,) if isinstance(keys, (str, int)) else keys

        first_key = keys[0]
        if first_key not in self.tree:
            self.tree[first_key] = Builder(core=self.core, schema=self.schema.get(first_key, {}))

        remaining = keys[1:]
        if len(remaining) > 0:
            self.tree[first_key].__setitem__(remaining, value)
        elif isinstance(value, dict):
            self.tree[first_key] = Builder(tree=value, core=self.core, schema=self.schema.get(first_key, {}))
        else:
            self.tree[first_key] = value

        # reset compiled composite
        self.compiled_composite = None

    def __getitem__(self, keys):
        # Convert single key to tuple
        keys = (keys,) if isinstance(keys, (str, int)) else keys

        first_key = keys[0]
        if first_key not in self.tree:
            self.tree[first_key] = Builder(parent=self, core=self.core, schema=self.schema.get(first_key, {}))

        remaining = keys[1:]
        if len(remaining) > 0:
            return self.tree[first_key].__getitem__(remaining)
        else:
            return self.tree[first_key]

    def list_types(self):
        return self.core.type_registry.list()

    def list_processes(self):
        print(self.core.process_registry.list())

    # def register(self, name, process, force=False):
    #     if not self.core.access(name) and isinstance(process, Edge):
    #         # TODO -- if process object is passed in, it has to be made into a schema and registered
    #         process_schema = {}
    #         warnings.warn(f"PROCESS SCHEMA INVALID.")
    #         self.core.register(name, process_schema, force=force)
    #     else:
    #         warnings.warn(f"PROCESS '{process}' FAILED TO REGISTER.")

    def add_process(
            self,
            name=None,
            config=None,
            inputs=None,
            outputs=None,
            **kwargs
    ):
        config = config or {}
        config.update(kwargs)
        edge_type = 'process'
        # address = self.core.process_registry.access(name)

        # make the schema
        initial_state = {
                '_type': edge_type,
                'address': f'local:{name}',  # TODO -- only support local right now?
                'config': config,
                'inputs': inputs or {},
                'outputs': outputs or {},
            }

        initial_schema = {'_type': edge_type}
        schema, state = self.core.complete(initial_schema, initial_state)

        self.tree = builder_tree_from_dict(state)
        self.schema = schema or {}

        # reset compiled composite
        self.compile()

    def connect(self, port=None, target=None):
        # assert self.schema.get('_type', {}) in EDGE_KEYS, f"Invalid type for connect: {self.schema}, needs to be in {EDGE_KEYS}"
        if port in self.schema['_inputs']:
            self.tree['inputs'][port] = target
        if port in self.schema['_outputs']:
            self.tree['outputs'][port] = target

        # reset compiled composite
        self.compile()

    def document(self):
        doc = self.core.serialize(
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
        # compile the top-level Builder
        if self.parent:
            return self.parent.compile()
        else:
            self.schema, tree = self.core.complete(
                self.schema,
                dict_from_builder_tree(self.tree)
            )
            self.compiled_composite = Composite({'state': tree, 'composition': self.schema})

            # reset the builder tree
            self.update_tree(self.compiled_composite.composition, self.compiled_composite.state)

            return self.compiled_composite

    def update_tree(self, schema=None, state=None):
        self.schema = schema or self.schema
        state = state or {}
        for k, i in state.items():
            if isinstance(i, dict):
                sub_schema = schema.get(k, {})
                self.tree[k].update_tree(sub_schema, i)
            else:
                self.tree[k] = i  # leaves

    def composite(self):
        return self.top().compiled_composite

    def run(self, interval):
        if not self.compiled_composite:
            self.compile()
        self.compiled_composite.run(interval)

    def ports(self):
        # self.compile()
        tree_dict = dict_from_builder_tree(self.tree)
        tree_type = tree_dict.get('_type')
        if not tree_type:
            warnings.warn(f"no type provided.")
        elif tree_type not in EDGE_KEYS:
            warnings.warn(f"Expected '_type' to be in {EDGE_KEYS}, found '{tree_type}' instead.")
        elif tree_type:
            return get_process_ports(tree_dict, self.schema)

    def visualize(self, filename=None, out_dir=None, **kwargs):
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

    def emitter(self, name='ram-emitter', emit_keys=None):

        address = self.core.address_registry(name)
        emitter_schema = {
            'emitter': {
                '_type': 'step',
                'address': address,
                'config': {
                    'emit': emit_keys or 'schema'   # TODO -- need more robust way to describe what gets emitted
                },
                'inputs': emit_keys or 'tree[any]'  # TODO -- these should be filled in automatically
            }
        }


def build_gillespie():
    from process_bigraph.experiments.minimal_gillespie import GillespieEvent  #, GillespieInterval

    gillespie = Builder()

    # first, what processes do we want and where do they come from
    gillespie.register_process(
        'GillespieEvent', GillespieEvent)
    gillespie.register_process(
        'GillespieInterval',
        address='local:!process_bigraph.experiments.minimal_gillespie.GillespieInterval',
    )
    # gillespie.register_process(
    #     'remote_copasi', address='biosimulators.COPASI', protocol='ray')
    # gillespie.register_process('lsoda_process',
    #                            # address='KISAO:0000088',  # this would use a KISAO protocol
    #                            address_config={
    #                                'repository': 'KISAO',  # this tells us how to
    #                                'address': '0000088',
    #                                'location': 'remote'})


    # build the bigraph
    gillespie.update_tree(state={'variables': [0, 1, 2]})  # this should allow us to set variables

    ## add processes
    gillespie['event_process'].add_process(
        name='GillespieEvent',
        kdeg=1.0,  # kwargs fill parameters in the config
    )
    gillespie['interval_process'].add_process(
        name='GillespieInterval',
        inputs={'port_id': ['store']}  # we should be able to set the wires directly like this
    )

    ## choose an emitter
    gillespie.emitter(name='ram-emitter', path=[])  # choose the emitter, path=[] would be all
    gillespie.emitter(name='csv-emitter', path=['cell1', 'internal'], emit_tree={})  # add a second emitter

    ## turn on emits (assume ram-emitter if none provided)
    gillespie['event_process'].emit(port='mRNA')  # this should turn on an emit from this port
    gillespie['interval_process'].emit(port='interval')

    ## connect the bigraph
    gillespie['event_process'].connect(input='DNA', target=['DNA_store'])
    gillespie['event_process'].connect(input='mRNA', target=['mRNA_store'])
    gillespie['interval_process'].connect(output='DNA', target=['DNA_store'])
    gillespie['interval_process'].connect(output='mRNA', target=['mRNA_store'])

    ## set some states
    gillespie['DNA_store'] = {'C': 2.0, 'G': 1.0}  # TODO this should check the type
    gillespie['mRNA_store'] = {'C': 0.0, 'G': 0.0}

    # TODO: move states from one location to another.
    # TODO: add custom types
    # TODO: add reactions, apply reactions to bigraph
    # TODO: update model subcomponents -- via config?

    # compile
    gillespie.compile()  # this fills and checks, this should also connect ports to stores with the same name, at the same level

    # plot the bigraph
    gillespie.visualize(filename='gillespie_bigraph')  # create bigraph plot

    # get the document
    doc = gillespie.document()

    # save the document
    gillespie.write(filename='gillespie1')

    # run simulation
    gillespie.run(10)
    results = gillespie.get_results()

    # This needs to work
    node = gillespie['path', 'to']
    node.add_process()


def test1():
    b = Builder()

    # @register_process('toy')
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

    b.register('toy', Toy)
    print(b.list_types())

    b['toy'].add_process(name='toy')

    # b.tree
    ports = b['toy'].ports()
    print(ports)
    # b.plot(filename='toy[1]')

    b['toy'].connect(port='A', target=['A_store'])
    b['A_store'] = 2.3
    b['toy'].connect(port='B', target=['B_store'])

    # plot the bigraph
    b.visualize(filename='toy[2]')

    b.write(filename='toy[2]', outdir='out')



if __name__ == '__main__':
    build_gillespie()
    # test1()
