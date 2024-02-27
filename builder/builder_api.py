import os
import json
import pprint
from bigraph_schema.registry import get_path, set_path
from process_bigraph import ProcessTypes, Composite
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
        return f"Builder(\n{pf(self.tree)})"

    def __getitem__(self, keys):
        return self.node[keys]

    def __setitem__(self, keys, value):
        self.node.__setitem__(keys, value)
        self.complete()

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


def test_builder():
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

    import ipdb; ipdb.set_trace()

    x = builder['down', 'here']
    assert x.value() == 10

    builder.visualize(filename='builder_test')

    # make composite, simulate
    composite = builder.generate()
    composite.run(10)

    # save document
    builder.write(filename='builder_test_doc')


if __name__ == '__main__':
    test_builder()
