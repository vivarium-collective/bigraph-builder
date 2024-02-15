"""
Bigraph Builder
================

API for building process bigraphs, integrating bigraph-schema, process-bigraph, and bigraph-viz under an intuitive
Python API.
"""
import os
import json
import warnings

from process_bigraph import Process, Step, Edge, Composite, ProcessTypes
from bigraph_schema.protocols import local_lookup_module
from bigraph_viz.diagram import plot_bigraph


EDGE_KEYS = ['process', 'step', 'edge']  # todo -- replace this with core.check() or similar


def custom_pf(d, indent=0):
    """Custom dictionary formatter to achieve specific indentation styles."""
    items = []
    for k, v in d.items():
        key_str = f"{repr(k)}: "
        if isinstance(v, dict):
            if v:  # Check if the dictionary is not empty
                value_str = custom_pf(v, indent + 3)
            else:
                value_str = "{}"
        else:
            value_str = repr(v)
        items.append(f"{' ' * indent}{key_str}{value_str}")

    # final formatting
    items_str = ',\n'.join(items)
    if indent > 0:
        return f"{{\n{items_str}\n{' ' * (indent - 4)}}}"
    else:
        return f"{{\n{items_str}\n}}"


def builder_tree_from_dict(d):
    d = d or {}
    builder_tree = {}
    for k, i in d.items():
        if isinstance(i, dict):
            builder_tree[k] = Builder(i)
        else:
            builder_tree[k] = i  # this is a leaf
    return builder_tree


def dict_from_builder_tree(builder_tree):
    tree = {}
    for k, i in builder_tree.items():
        if isinstance(i, Builder):
            tree[k] = dict_from_builder_tree(i.builder_tree)
        else:
            tree[k] = i  # this is a leaf
    return tree


def get_process_ports(value, schema):
    ports = {}
    if value.get('_type') in EDGE_KEYS:
        ports['_inputs'] = schema.get('_inputs', {})
        ports['_outputs'] = schema.get('_outputs', {})
    return ports


def merge_dicts(original, new):
    # TODO -- check this
    for k, v in new.items():
        if k not in original:
            original[k] = v
        elif isinstance(v, dict):
            original[k] = merge_dicts(original[k], v)
        else:
            original[k] = v
    return original


class Builder(dict):

    def __init__(self, tree=None, schema=None, parent=None, core=None):
        super().__init__()
        self.builder_tree = builder_tree_from_dict(tree)
        self.schema = schema or {}  # TODO -- need to track schema
        self.core = core or ProcessTypes()
        self.parent = parent

        self.compiled_composite = None
        # TODO -- add an emitter by default so results are automatic

    def get(self, key, default=None):
        if key in self.builder_tree:
            return self.builder_tree[key]
        else:
            return default

    def get_tree(self):
        return dict_from_builder_tree(self.builder_tree)

    def register_process(self, process_name, address=None):
        """
        Register processes into the local core type system
        """
        assert isinstance(process_name, str), f'Process name must be a string: {process_name}'

        if address is None:  # use as a decorator
            def decorator(cls):
                if not issubclass(cls, Edge):
                    raise TypeError(f"The class {cls.__name__} must be a subclass of Edge")
                self.core.process_registry.register(process_name, cls, force=True)
                return cls
            return decorator

        else:

            # Check if address is a string
            if isinstance(address, str):
                protocol, addr = address.split(':', 1)
                if protocol != 'local':
                    raise ValueError('BigraphBuilder only supports the local protocol in the current version')

                if addr.startswith('!'):
                    process_class = local_lookup_module(addr[1:])
                    self.core.process_registry.register(process_name, process_class, force=True)
                else:
                    raise ValueError('Only local addresses starting with "!" are supported')

            # Check if address is a class object
            elif issubclass(address, Edge):
                self.core.process_registry.register(process_name, address, force=True)
            else:
                raise TypeError(f"Unsupported address type for {process_name}: {type(address)}. Registration failed.")

    def top(self):
        # recursively get the top parent
        if self.parent:
            return self.parent.top()
        else:
            return self

    def __repr__(self):
        return custom_pf(self.get_tree())
        # return f"Builder(\n{pf(self.tree)})"

    def __setitem__(self, keys, value):
        # Convert single key to tuple
        keys = (keys,) if isinstance(keys, (str, int)) else keys
        first_key = keys[0]
        remaining = keys[1:]

        if first_key not in self.builder_tree:
            self.builder_tree[first_key] = Builder(core=self.core)
        if len(remaining) > 0:
            self.builder_tree[first_key].__setitem__(remaining, value)
        elif isinstance(value, dict):
            self.builder_tree[first_key] = Builder(tree=value,
                                                   core=self.core,
                                                   schema=self.schema[first_key])
        else:
            self.builder_tree[first_key] = value

        # # reset compiled composite
        # self.compiled_composite = None

    def __getitem__(self, keys):
        # Convert single key to tuple
        keys = (keys,) if isinstance(keys, (str, int)) else keys

        first_key = keys[0]
        if first_key not in self.builder_tree:
            self.builder_tree[first_key] = Builder(parent=self, core=self.core, schema=self.schema.get(first_key, {}))

        remaining = keys[1:]
        if len(remaining) > 0:
            return self.builder_tree[first_key].__getitem__(remaining)
        else:
            return self.builder_tree[first_key]

    def list_types(self):
        return self.core.type_registry.list()

    def list_processes(self):
        print(self.core.process_registry.list())

    def add_process(
            self,
            name=None,
            config=None,
            inputs=None,
            outputs=None,
            **kwargs
    ):
        """
        Add a process to the tree
        """
        config = config or {}
        config.update(kwargs)
        edge_type = 'process'  # TODO -- don't hardcode as process

        # make the schema
        initial_state = {
                '_type': edge_type,
                'address': f'local:{name}',  # TODO -- only support local right now?
                'config': config,
                'inputs': inputs or {},
                'outputs': outputs or {},
            }

        initial_schema = {'_type': edge_type}
        self.schema, state = self.core.complete(initial_schema, initial_state)
        self.builder_tree = builder_tree_from_dict(state)

        # complete the composite
        self.complete()

    def complete(self):
        if self.parent:
            return self.parent.complete()
        else:
            schema, tree = self.core.complete(self.schema, self.get_tree())
            self.schema = merge_dicts(self.schema, schema)
            # self.builder_tree = merge_dicts(self.builder_tree, builder_tree_from_dict(tree))

            # TODO -- we may want to go through and update the existing schema and tree rather than completely redoing them...
            # self.schema = schema
            self.builder_tree = builder_tree_from_dict(tree)

    def connect_all(self):
        self.complete()  # this will get the schema
        tree = self.get_tree()
        for k, v in tree.items():
            if isinstance(v, dict):
                if v.get('_type') in EDGE_KEYS:
                    for port in self.schema[k]['_inputs'].keys():
                        if port not in v.get('inputs', {}):
                            self.builder_tree[k].connect(port=port, target=[port])
                    for port in self.schema[k]['_outputs'].keys():
                        if port not in v.get('outputs', {}):
                            self.builder_tree[k].connect(port=port, target=[port])
                else:
                    pass
                    # v.connect_all()
                # TODO -- propagate down

    def connect(self, port=None, target=None):
        assert self.core.check('edge', self.get_tree())
        self.complete()
        if port in self.schema['_inputs']:
            self.builder_tree['inputs'][port] = target
        if port in self.schema['_outputs']:
            self.builder_tree['outputs'][port] = target

    def document(self):
        doc = self.core.serialize(
            self.schema,
            self.get_tree())
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
                self.get_tree()
            )
            self.compiled_composite = Composite(
                {'state': tree, 'composition': self.schema},
                core=self.core)

            # reset the builder tree
            self.update_tree(self.compiled_composite.composition, self.compiled_composite.state)

            return self.compiled_composite

    def update_tree(self, schema=None, state=None):
        self.schema = schema or self.schema  # TODO -- should we be merging the schema?
        state = state or {}
        for k, i in state.items():
            if isinstance(i, dict):
                sub_schema = schema.get(k, {})
                self.builder_tree[k].update_tree(sub_schema, i)
            else:
                self.builder_tree[k] = i  # this is a leaf

    def composite(self):
        return self.top().compiled_composite

    def run(self, interval):
        if not self.compiled_composite:
            self.compile()
        self.compiled_composite.run(interval)

    def ports(self, print_ports=False):
        # self.compile()
        tree_dict = self.get_tree()
        tree_type = tree_dict.get('_type')
        if not tree_type:
            warnings.warn(f"no type provided.")
        elif tree_type not in EDGE_KEYS:
            warnings.warn(f"Expected '_type' to be in {EDGE_KEYS}, found '{tree_type}' instead.")
        elif tree_type:
            process_ports = get_process_ports(tree_dict, self.schema)
            if not print_ports:
                return process_ports
            else:
                print(custom_pf(process_ports))

    def visualize(self, filename=None, out_dir=None, **kwargs):
        return plot_bigraph(
            self.get_tree(),
            schema=self.schema,
            core=self.core,
            out_dir=out_dir,
            filename=filename,
            # show_process_schema=False,
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
    from process_bigraph.experiments.minimal_gillespie import GillespieEvent #, GillespieInterval

    gillespie = Builder()

    # first, what processes do we want and where do they come from
    gillespie.register_process(
        'GillespieEvent', GillespieEvent)
    gillespie.register_process(
        'GillespieInterval',
        address='local:!process_bigraph.experiments.minimal_gillespie.GillespieInterval',
    )
    # gillespie.register_process('remote_copasi', address='biosimulators.COPASI', protocol='ray')
    # gillespie.register_process('lsoda_process', address='KISAO:0000088'})  # this would use a KISAO protocol

    # build the bigraph
    # gillespie.update_tree(state={'variables': [0, 1, 2]})  # this should allow us to set variables

    ## add processes
    gillespie['event_process'].add_process(
        name='GillespieEvent',
        kdeg=1.0,  # kwargs fill parameters in the config
    )
    gillespie['interval_process'].add_process(
        name='GillespieInterval',
        # inputs={'port_id': ['store']}  # we should be able to set the wires directly like this
    )

    gillespie['event_process'].connect(port='mRNA', target=['mRNA_store'])

    gillespie.connect_all()  # This can maybe be used to connect all ports to stores of the same name?

    gillespie.complete()
    gillespie.compile()

    ## visualize part-way through build
    gillespie.visualize(filename='bigraph1', out_dir='out')

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

    @b.register_process('toy')
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

    # b.register('toy', Toy)
    # print(b.list_types())
    #
    # b['toy'].add_process(name='toy')
    #
    # # b.tree
    # ports = b['toy'].ports()
    # print(ports)
    # # b.plot(filename='toy[1]')
    #
    # b['toy'].connect(port='A', target=['A_store'])
    # b['A_store'] = 2.3
    # b['toy'].connect(port='B', target=['B_store'])
    #
    # # plot the bigraph
    # b.visualize(filename='toy[2]')
    #
    # b.write(filename='toy[2]', outdir='out')



if __name__ == '__main__':
    build_gillespie()
    # test1()
