import tasks
from utils import *
from influence import *
from copy import copy
import hashlib
import tools
import networkx as nx
import log
import utils


class TaskProxy(object):
    def __init__(self, task):
        self.task = task
        self.children = []
        self.ancestors = []

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
    @cached.instance
    def identity(self):
        sha = hashlib.sha1()
        HashInfluenceRegistry.get().apply_all(self.task, sha)

        for node in self.children:
            sha.update(node.identity)

        return sha.hexdigest()

    def __str__(self):
        return "{} [{}]".format(self.task.name, ", ".join([node.task.name for node in self.children]))

    def has_children(self):
        return len(self.children) > 0

    def has_ancestors(self):
        return len(self.ancestors) > 0

    def finalize(self, dag):
        self.children = nx.descendants(dag, self)
        self.anestors = nx.ancestors(dag, self)
        return self.identity

    def run(self, cache):
        if cache.is_available_remotely(self):
            cache.download(self)

        if not cache.is_available_locally(self):
            with cache.get_context(self) as context:
                self.task.run(context, tools)

            with cache.get_artifact(self) as artifact:
                self.task.publish(artifact)
                artifact.commit()

            assert cache.upload(self), \
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
    
    

class GraphBuilder(object):
    @staticmethod
    def build(task_list):
        nodes = [TaskProxy(task) for task in task_list]
        nodes = {node.name: node for node in nodes}

        task_registry = tasks.TaskRegistry.get()
        
        graph = Graph()
        queue = copy(nodes.values())
        while queue:
            parent = queue.pop()

            if not graph.has_node(parent):
                graph.add_node(parent)

            for requirement in as_list(parent.task._get_requires()):
                child = nodes.get(requirement) or TaskProxy(task_registry.get_task(requirement))
                nodes[requirement] = child
                queue.append(child)
                
                graph.add_node(child)
                graph.add_edges_from([(parent, child)])

        #print([n.name for n in graph.nodes])
        #print([(n1.name, n2.name) for n1, n2 in graph.edges])
        assert nx.is_directed_acyclic_graph(graph), "cyclic graph"

        map(lambda x: x.finalize(graph), graph.nodes)
        return graph


class GraphDFIterator(object):
    @staticmethod
    def as_list(graph):
        done = set()
        l = []
        q = copy(graph) if type(graph) == list else [graph]
        while q:
            n = q.pop()
            if n not in done:
                l.append(n)
            done.add(n)
            q.extend(n.children)
        return l
    
    @staticmethod
    def iterate(graph, predicate):
        for node in reversed(GraphDFIterator.as_list(graph)):
            predicate(node)

