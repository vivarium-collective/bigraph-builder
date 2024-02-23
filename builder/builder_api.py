from bigraph_schema.registry import get_path, set_path
from process_bigraph import ProcessTypes


def builder_tree_from_dict(
        builder,
        schema,
        tree,
        path=()
):
    # TODO -- this might need to use core.fold()
    builder_tree = BuilderNode(builder, path)
    if isinstance(tree, dict):
        for key, sub_tree in tree.items():
            next_path = path + (key,)
            builder_tree.branches[key] = builder_tree_from_dict(
                builder=builder,
                schema=schema.get(key, schema) if schema else {},
                tree=sub_tree,
                path=next_path)
    return builder_tree


class BuilderNode:

    def __init__(self, builder, path):
        self.builder = builder
        self.path = path
        self.branches = {}

    def __getitem__(self, keys):
        # Convert single key to tuple
        keys = (keys,) if isinstance(keys, (str, int)) else keys
        first_key = keys[0]
        if first_key not in self.branches:
            self.branches[first_key] = BuilderNode(
                builder=self.builder,
                path=self.path + (first_key,))

        remaining = keys[1:]
        if len(remaining) > 0:
            return self.branches[first_key].__getitem__(remaining)
        else:
            return self.branches[first_key]

    def __setitem__(self, keys, value):
        # Convert single key to tuple
        keys = (keys,) if isinstance(keys, (str, int)) else keys
        first_key = keys[0]
        remaining = keys[1:]
        path_here = self.path + (first_key,)

        if first_key not in self.branches:
            self.branches[first_key] = BuilderNode(
                builder=self.builder,
                path=path_here)

        if len(remaining) > 0:
            self.branches[first_key].__setitem__(remaining, value)
        elif isinstance(value, dict):
            # if '_type' in value

            self.branches[first_key] = builder_tree_from_dict(
                builder=self.builder,
                schema=self.get_schema(),
                tree=value,
                path=path_here)
        else:
            # set the value
            set_path(tree=self.builder.tree, path=path_here, value=value)

    def get_tree(self):
        return get_path(self.builder.tree, self.path)

    def get_schema(self):
        return get_path(self.builder.schema, self.path)

    def top(self):
        return self.builder.builder_tree


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
        self.builder_tree = builder_tree_from_dict(self, self.schema, self.tree)

    def __getitem__(self, keys):
        return self.builder_tree[keys]

    def __setitem__(self, keys, value):
        self.builder_tree.__setitem__(keys, value)
        self.complete()

    def complete(self):
        self.schema, self.tree = self.core.complete(self.schema, self.tree)



def test_builder():
    core = ProcessTypes()

    initial_tree = {
        'DNA_store': {
            '_type': 'map[float]',
            'A gene': 2.0,
            'B gene': 1.0}}

    b = Builder(core=core, tree=initial_tree)

    # test set/get
    b['down', 'here'] = {'_value': 10, '_type': 'integer'}
    x = b['down', 'here']
    # assert x.get_tree() == 10
    x


if __name__ == '__main__':
    test_builder()
