from tasks import *
from utils import *
from influence import *
from copy import copy
import hashlib
import tools
import networkx as nx
from networkx.drawing.nx_agraph import write_dot
import log
import utils


class TaskProxy(object):
    def __init__(self, task):
        self.task = task
        self.children = []
        self.ancestors = []
        self.extends = []

        self._extended_by = 0
        self._completed_by = 0
        self._in_progress = False
        self._completed = False

    @property
    def name(self):
        return self.task.name

    @property
    def canonical_name(self):
        return self.task.name.replace("/", "_")

    @property
    def qualified_name(self):
        return utils.format_task_name(self.task.name, self.task._get_parameters())

    @property
    def log_name(self):
        return "({} {})".format(self.qualified_name, self.identity[:8])

    @property
    @cached.instance
    def identity(self):
        sha = hashlib.sha1()

        with tools.cwd(self.task.joltdir):
            HashInfluenceRegistry.get().apply_all(self.task, sha)

        for node in self.children:
            sha.update(node.identity)

        return sha.hexdigest()

    def __str__(self):
        return "{}{}".format(self.qualified_name, "*" if self.is_extended() else '')

    def __hash__(self):
        return hash(self.qualified_name)

    def info(self, fmt, *args, **kwargs):
        self.task.info(fmt + " " + self.log_name, *args, **kwargs)

    def error(self, fmt, *args, **kwargs):
        self.task.error(fmt + " " + self.log_name, *args, **kwargs)

    def has_children(self):
        return len(self.children) > 0

    def has_ancestors(self):
        return len(self.ancestors) > 0

    def is_cacheable(self):
        return self.task.is_cacheable()

    def is_resource(self):
        return isinstance(self.task, Resource)

    def is_extended(self):
        return self._extended_by > 0

    def add_extends(self, task):
        return self.extends.append(task)

    def in_progress(self):
        return self._in_progress

    def is_ready(self, dag):
        if self.is_extended():
            return False

        if self.in_progress():
            return False

        neighbors = set([n for n in dag.neighbors(self)])
        if neighbors:
            if all([n in self.extends for n in neighbors]):
                return all([dag.is_leaf(n) for n in self.extends])
            return False
        return True

    def is_completed(self):
        return self._completed

    def set_extended(self):
        self._extended_by += 1

    def set_in_progress(self):
        self._in_progress = True

    def set_completed(self, dag):
        if self.is_extended():
            self._completed_by += 1
        if self._extended_by > self._completed_by:
            return

        self._completed = True
        dag.remove_node(self)
        for extended in self.extends:
            if not extended.is_completed():
                extended.set_completed(dag)

    def finalize(self, dag):
        # Find all direct and transitive dependencies
        self.children = sorted(nx.descendants(dag, self), key=lambda t: t.qualified_name)

        # Exclude transitive resources dependencies
        self.children = filter(
            lambda n: not n.is_resource() or dag.are_neighbors(self, n),
            self.children)

        self.anestors = nx.ancestors(dag, self)
        return self.identity

    def started(self):
        self.info("Execution started")
        self.duration = utils.duration()

    def run(self, cache, force_upload=False, force_build=False):
        if cache.is_available_remotely(self):
            cache.download(self)

        if not cache.is_available_locally(self) or force_build:
            t = TaskTools(self)

            for extended in self.extends:
                extended.run(cache, force_upload, force_build=True)

            with cache.get_context(self) as context:
                with t.cwd(self.task.joltdir):
                    self.task.run(context, t)

            if force_build and cache.is_available_locally(self):
                with cache.get_artifact(self) as artifact:
                    artifact.discard()

            with cache.get_artifact(self) as artifact:
                with t.cwd(self.task.joltdir):
                    self.task.publish(artifact, t)
                artifact.commit()

            assert cache.upload(self, force=force_upload), \
                "Failed to upload artifact for {}".format(self.name)
                


class Graph(nx.DiGraph):
    def __init__(self):
        super(Graph, self).__init__()

    def prune(self, func):
        for node in [n for n in self.nodes]:
            log.hysterical("[GRAPH] Checking {} ({})", node.name, node.identity)
            if func(self, node):
                log.hysterical("[GRAPH] Pruned {}", node.name)
                self.remove_node(node)

    def select(self, func):
        return [n for n in self.nodes if func(self, n)]

    def is_leaf(self, node):
        return self.out_degree(node) == 0
    
    def is_root(self, node):
        return self.in_degree(node) == 0

    def are_neighbors(self, n1, n2):
        return n2 in self[n1]


class GraphBuilder(object):
    def __init__(self):
        self.graph = Graph()
        self.nodes = {}
        self.registry = tasks.TaskRegistry.get()

    def _get_node(self, name):
        node = self.nodes.get(name)
        if not node:
            task = self.registry.get_task(name)
            node = self._build_node(TaskProxy(task))
            self.nodes[name] = node
        return node
        
    def _build_node(self, node):
        self.graph.add_node(node)

        for requirement in node.task._get_requires():
            child = self._get_node(requirement)
            self.graph.add_edges_from([(node, child)])

        for extend in node.task._get_extends():
            extend_node = self._get_node(extend)
            for requirement in extend_node.task._get_requires():
                child = self._get_node(requirement)
                self.graph.add_edges_from([(node, child)])
            self.graph.add_edges_from([(node, extend_node)])
            extend_node.set_extended()
            node.add_extends(extend_node)

        node.finalize(self.graph)
        return node

    def build(self, task_list):
        proxies = [TaskProxy(task) for task in task_list]
        self.nodes = {node.qualified_name: node for node in proxies}

        for node in copy(self.nodes.values()):
            node = self._build_node(node)

        assert nx.is_directed_acyclic_graph(self.graph), "cyclic graph"
        return self.graph

    def display(self):
        with tools.tmpdir("dot") as t:
            with tools.cwd(t.get_path()):
                write_dot(self.graph, 'graph.dot')
                tools.run('dot -Tsvg graph.dot -o graph.svg')
                tools.run('eog graph.svg')
