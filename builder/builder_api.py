import os
import json
import pprint
from bigraph_schema.registry import get_path, set_path
from bigraph_schema import Edge
from bigraph_schema.protocols import local_lookup_module
from process_bigraph import Process, Step, Composite, ProcessTypes
from bigraph_viz.diagram import plot_bigraph


pretty = pprint.PrettyPrinter(indent=2)


def pf(x):
    return pretty.pformat(x)


def node_from_tree(
        builder,
        schema,
        tree,
        path=()
):
    # TODO -- this might need to use core.fold()
    node = BuilderNode(builder, path)
    if isinstance(tree, dict):
        for key, subtree in tree.items():
            next_path = path + (key,)
            node.branches[key] = node_from_tree(
                builder=builder,
                schema=schema.get(key, schema) if schema else {},
                tree=subtree,
                path=next_path)

    return node


class BuilderNode:

    def __init__(self, builder, path):
        self.builder = builder
        self.path = path
        self.branches = {}

    def __repr__(self):
        tree = self.value()
        return f"BuilderNode({pf(tree)})"

    def __getitem__(self, keys):
        # Convert single key to tuple
        keys = (keys,) if isinstance(keys, (str, int)) else keys
        head = keys[0]
        if head not in self.branches:
            self.branches[head] = BuilderNode(
                builder=self.builder,
                path=self.path + (head,))

        tail = keys[1:]
        if len(tail) > 0:
            return self.branches[head].__getitem__(tail)
        else:
            return self.branches[head]


    def __setitem__(self, keys, value):
        # Convert single key to tuple
        keys = (keys,) if isinstance(keys, (str, int)) else keys
        head = keys[0]
        tail = keys[1:]
        path_here = self.path + (head,)

        if head not in self.branches:
            self.branches[head] = BuilderNode(
                builder=self.builder,
                path=path_here)

        if len(tail) > 0:
            self.branches[head].__setitem__(tail, value)
        elif isinstance(value, dict):
            if '_type' in value:
                set_path(
                    tree=self.builder.schema,
                    path=path_here,
                    value=value['_type'])

            if '_value' in value:
                set_path(
                    tree=self.builder.tree,
                    path=path_here,
                    value=value['_value'])

                self.branches[head] = BuilderNode(
                    builder=self.builder,
                    path=path_here)

            else:
                self.branches[head] = node_from_tree(
                    builder=self.builder,
                    schema=self.schema(),
                    tree=value,
                    path=path_here)
        else:
            # set the value
            set_path(tree=self.builder.tree, path=path_here, value=value)


    def value(self):
        return get_path(self.builder.tree, self.path)


    def schema(self):
        return get_path(self.builder.schema, self.path)


    def top(self):
        return self.builder.node

    def add_process(
            self,
            name,
            config=None,
            inputs=None,
            outputs=None,
            edge_type=None,
            **kwargs
    ):
        """ Add a process to the tree """
        # TODO -- assert this process is in the process_registry

        assert name, 'add_process requires a name as input'
        config = config or {}
        config.update(kwargs)
        edge_type = edge_type or 'process'  # TODO -- don't hardcode as process

        # make the process spec
        state = {
            '_type': edge_type,
            'address': f'local:{name}',  # TODO -- only support local right now?
            'config': config,
            'inputs': {} if inputs is None else inputs,
            'outputs': {} if outputs is None else outputs,
        }

        set_path(tree=self.builder.tree, path=self.path, value=state)



class Builder:

    def __init__(
            self,
            schema=None,
            tree=None,
            core=None,
    ):
        schema = schema or {}
        tree = tree or {}

        self.core = core or ProcessTypes()
        self.schema, self.tree = self.core.complete(schema, tree)
        self.node = node_from_tree(self, self.schema, self.tree)

    def __repr__(self):
        return f"Builder({pf(self.tree)})"

    def __getitem__(self, keys):
        return self.node[keys]

    def __setitem__(self, keys, value):
        self.node.__setitem__(keys, value)
        self.complete()

    def list_types(self):
        return self.core.type_registry.list()

    def list_processes(self):
        print(self.core.process_registry.list())

    def complete(self):
        self.schema, self.tree = self.core.complete(self.schema, self.tree)

    def visualize(self, filename=None, out_dir=None, **kwargs):
        return plot_bigraph(
            state=self.tree,
            schema=self.schema,
            core=self.core,
            out_dir=out_dir,
            filename=filename,
            **kwargs)

    def generate(self):
        composite = Composite({
            'state': self.tree,
            'composition': self.schema
        },
            core=self.core)

        return composite

    def document(self):
        return self.core.serialize(
            self.schema,
            self.tree)

    def write(self, filename, outdir='out'):
        if not os.path.exists(outdir):
            os.makedirs(outdir)

        filepath = f"{outdir}/{filename}.json"
        document = self.document()

        # Writing the dictionary to a JSON file
        with open(filepath, 'w') as json_file:
            json.dump(document, json_file, indent=4)

        print(f"File '{filename}' successfully written in '{outdir}' directory.")

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


def test_builder():
    from process_bigraph.experiments.minimal_gillespie import GillespieEvent  # , GillespieInterval

    core = ProcessTypes()

    initial_tree = {
        'DNA_store': {
            '_type': 'map[float]',
            'A gene': 2.0,
            'B gene': 1.0},
        'RNA_store': {
            '_type': 'map[float]',
            'A rna': 0.0,
            'B rna': 0.0},
    }

    builder = Builder(core=core, tree=initial_tree)

    # test set/get
    builder['DNA_store', 'C gene'] = 3.0
    assert builder['DNA_store', 'C gene'].value() == 3.0

    builder['down', 'here'] = {
        '_value': 10,
        '_type': 'integer'}

    x = builder['down', 'here']
    assert x.value() == 10

    # add processes
    print(f"available processes: {builder.list_processes()}")

    ## register processes by name: what processes do we want and where do they come from
    builder.register_process(
        'GillespieEvent', GillespieEvent)
    builder.register_process(
        'GillespieInterval',
        address='local:!process_bigraph.experiments.minimal_gillespie.GillespieInterval')

    ## add processes
    builder['event_process'].add_process(
        name='GillespieEvent',
        kdeg=1.0,  # kwargs fill parameters in the config
    )
    builder['interval_process'].add_process(
        name='GillespieInterval',
        # inputs={'port_id': ['store']}  # we should be able to set the wires directly like this
    )




    # make bigraph-viz diagram
    builder.visualize(filename='builder_test',
                      show_values=True,
                      show_types=True)

    # make composite, simulate
    composite = builder.generate()
    composite.run(10)

    # save document
    builder.write(filename='builder_test_doc')


if __name__ == '__main__':
    test_builder()
