from contextlib import contextmanager
import hashlib
import networkx as nx
from threading import RLock

from jolt.tasks import Resource, Export
#from jolt.utils import *
from jolt.influence import HashInfluenceRegistry
from jolt import log
from jolt import utils
from jolt import colors
from jolt import hooks
from jolt import tools
from jolt import filesystem as fs
from jolt.error import raise_error_if
from jolt.error import raise_task_error_if

class TaskProxy(object):
    def __init__(self, task, graph):
        self.task = task
        self.graph = graph
        self.children = []
        self.ancestors = []
        self.extensions = []
        self.duration_queued = None
        self.duration_running = None

        self._extended_task = None
        self._in_progress = False
        self._completed = False
        self._identity = None
        self._frozen = False

    def __hash__(self):
        return id(self)

    @property
    def tools(self):
        return self.task.tools

    @property
    def name(self):
        return self.task.name

    @property
    def canonical_name(self):
        return self.task.canonical_name

    @property
    def qualified_name(self):
        return utils.format_task_name(
            self.task.name,
            self.task._get_parameters())

    @property
    def short_qualified_name(self):
        return utils.format_task_name(
            self.task.name,
            self.task._get_explicitly_set_parameters())

    @property
    def log_name(self):
        return "({0} {1})".format(self.short_qualified_name, self.identity[:8])

    @property
    def identity(self):
        if self._identity is not None:
            return self._identity

        sha = hashlib.sha1()

        HashInfluenceRegistry.get().apply_all(self.task, sha)

        # print("{}: {}".format(self.name, [n.name for n in self.children]))
        for node in self.children:
            sha.update(node.identity.encode())

        if self._extended_task:
            sha.update(self._extended_task.identity.encode())

        self._identity = sha.hexdigest()
        self.task.identity = self._identity
        return self._identity

    @identity.setter
    def identity(self, value):
        self._frozen = True
        self._identity = value
        self.task.identity = self._identity

    def __str__(self):
        return "{0}{1}".format(self.short_qualified_name, "*" if self.is_extension() else '')

    def info(self, fmt, *args, **kwargs):
        self.task.info(fmt + " " + self.log_name, *args, **kwargs)

    def warn(self, fmt, *args, **kwargs):
        self.task.warn(fmt + " " + self.log_name, *args, **kwargs)

    def error(self, fmt, *args, **kwargs):
        self.task.error(fmt + " " + self.log_name, *args, **kwargs)

    def has_children(self):
        return len(self.children) > 0

    def has_ancestors(self):
        return len(self.ancestors) > 0

    def is_frozen(self):
        return self._frozen

    def is_cacheable(self):
        return self.task.is_cacheable()

    def is_resource(self):
        return isinstance(self.task, Resource)

    def has_artifact(self):
        return not self.is_resource()

    def has_extensions(self):
        return len(self.extensions) > 0

    def add_extension(self, task):
        if self.is_extension():
            self._extended_task.add_extension(task)
        else:
            self.extensions.append(task)

    def is_extension(self):
        return self._extended_task is not None

    def set_extended_task(self, task):
        self._extended_task = task

    def get_extended_task(self):
        if self.is_extension():
            return self._extended_task.get_extended_task()
        return self

    def is_available_locally(self, cache):
        tasks = [self] + self.extensions
        return all(map(cache.is_available_locally, tasks))

    def is_available_remotely(self, cache):
        tasks = [self] + self.extensions
        return all(map(cache.is_available_remotely, tasks))

    def is_uploadable(self, cache):
        tasks = [self] + self.extensions
        return all(map(cache.is_uploadable, tasks))

    def is_fast(self):
        tasks = [self.task] + [e.task for e in self.extensions]
        return all([task.fast for task in tasks])

    def in_progress(self):
        return self._in_progress

    def is_ready(self):
        if self.in_progress():
            return False

        if self.is_extension():
            return False

        return self.graph.is_leaf(self)

    def is_completed(self):
        return self._completed

    def set_in_progress(self):
        self._in_progress = True

    def finalize(self, dag, manifest):
        log.verbose("Finalizing: " + self.short_qualified_name)
        self.manifest = manifest

        # Find all direct and transitive dependencies
        self.descendants = sorted(
            nx.descendants(dag, self),
            key=lambda t: t.qualified_name)

        # Exclude transitive resources dependencies
        self.children = list(
            filter(lambda n: not n.is_resource() or \
                   dag.are_neighbors(self, n),
                   self.descendants))

        self.ancestors = nx.ancestors(dag, self)

        task = self.manifest.find_task(self.qualified_name)
        if task is not None:
            if task.identity:
                self.identity = task.identity
            for attrib in task.attributes:
                export = utils.getattr_safe(self.task, attrib.name)
                assert isinstance(export, Export), \
                    "'{0}' is not an exportable attribute of task '{1}'"\
                    .format(attrib.name, self.qualified_name)
                export.assign(attrib.value)

        return self.identity

    def started(self, what="Execution"):
        self.task.info(colors.blue(what + " started " + self.log_name))
        self.duration_queued = utils.duration()
        self.duration_running = utils.duration()
        hooks.task_started(self)

    def running(self):
        self.duration_running = utils.duration()

    def failed(self, what="Execution"):
        self.error("{0} failed after {1} {2}", what,
                   self.duration_running,
                   self.duration_queued.diff(self.duration_running))
        hooks.task_failed(self)

    def finished(self, what="Execution"):
        assert not self._completed, "task has already been completed"
        self._completed = True
        try:
            self.graph.remove_node(self)
        except:
            self.warn("Pruned task was executed")
        self.task.info(colors.green(what + " finished after {0} {1}" + self.log_name),
                       self.duration_running,
                       self.duration_queued.diff(self.duration_running))
        hooks.task_finished(self)

    def skipped(self):
        self._completed = True
        try:
            self.graph.remove_node(self)
        except:
            self.warn("Pruned task was executed")

    def clean(self, cache, expired):
        with self.tools:
            self.task.clean(self.tools)
            discarded = cache.discard(self, expired)
            if discarded:
                log.verbose("Discarded: {} ({})", self.short_qualified_name, self.identity[:8])
            else:
                log.verbose(" Retained: {} ({})", self.short_qualified_name, self.identity[:8])

    def run(self, cache, force_upload=False, force_build=False):
        with self.tools:
            tasks = [self] + self.extensions
            available_locally = available_remotely = False

            for child in self.children:
                if not child.has_artifact():
                    continue
                if not cache.is_available_locally(child):
                    raise_task_error_if(
                        not cache.download(child),
                        child, "failed to download task artifact")

            if not force_build:
                available_locally = all(map(cache.is_available_locally, tasks))
                if available_locally and not force_upload:
                    return
                available_remotely = all(map(cache.is_available_remotely, tasks))
                if not available_locally and available_remotely:
                    available_locally = cache.download(self)

            if force_build or not available_locally:
                with log.threadsink() as buildlog:
                    with cache.get_context(self) as context:
                        with self.tools.cwd(self.task.joltdir):
                            self.task.run(context, self.tools)

                    if cache.is_available_locally(self):
                        with cache.get_artifact(self) as artifact:
                            artifact.discard()

                    with cache.get_artifact(self) as artifact:
                        with self.tools.cwd(self.task.joltdir):
                            self.task.publish(artifact, self.tools)
                        with open(fs.path.join(artifact.path, ".build.log"), "w") as f:
                            f.write(buildlog.getvalue())
                        artifact.commit()

            if force_build or force_upload or not available_remotely:
                raise_task_error_if(
                    not cache.upload(self, force=force_upload) and cache.upload_enabled(),
                    self, "failed to upload task artifact")

            for extension in self.extensions:
                try:
                    extension.started()
                    extension.running()
                    extension.run(cache, force_upload, force_build)
                except Exception as e:
                    extension.failed()
                    raise e
                else:
                    extension.finished()


class Graph(nx.DiGraph):
    def __init__(self):
        super(Graph, self).__init__()
        self._mutex = RLock()

    def remove_node(self, node):
        with self._mutex:
            super(Graph, self).remove_node(node)

    @property
    def tasks(self):
        with self._mutex:
            return [n for n in self.nodes]

    def has_tasks(self):
        with self._mutex:
            return len(self.nodes) > 0

    def get_task(self, qualified_name):
        with self._mutex:
            return self._nodes_by_name.get(qualified_name)

    def prune(self, func):
        with self._mutex:
            for node in nx.topological_sort(self):
                if func(self, node):
                    log.debug("[GRAPH] Pruned {0}", node.short_qualified_name)
                    self.remove_node(node)

            for node in self.nodes:
                log.debug("[GRAPH] Keeping {0} ({1})", node.qualified_name, node.identity)

    def select(self, func):
        with self._mutex:
            return [n for n in self.nodes if func(self, n)]

    def debug(self):
        with self._mutex:
            log.verbose("[GRAPH] Listing all nodes")
            for node in nx.topological_sort(self):
                log.verbose("[GRAPH]   " + node.qualified_name)

    def is_leaf(self, node):
        with self._mutex:
            return self.out_degree(node) == 0

    def is_root(self, node):
        with self._mutex:
            return self.in_degree(node) == 0

    def is_orphan(self, node):
        with self._mutex:
            return self.is_root(node) and self.is_leaf(node)

    def are_neighbors(self, n1, n2):
        with self._mutex:
            return n2 in self[n1]


class GraphBuilder(object):
    def __init__(self, registry, manifest, progress=False):
        self.graph = Graph()
        self.nodes = {}
        self.registry = registry
        self.manifest = manifest
        self.progress = progress

    def _get_node(self, name):
        node = self.nodes.get(name)
        if not node:
            task = self.registry.get_task(name)
            node = self._build_node(TaskProxy(task, self.graph))
            self.nodes[name] = node
        return node

    def _build_node(self, node):
        self.graph.add_node(node)

        if node.task.extends:
            extended_node = self._get_node(node.task.extends)
            self.graph.add_edges_from([(node, extended_node)])
            node.set_extended_task(extended_node)
            extended_node.add_extension(node)
            parent = extended_node.get_extended_task()
        else:
            parent = node

        for requirement in node.task.requires:
            child = self._get_node(requirement)
            self.graph.add_edges_from([(parent, child)])

        return node

    @contextmanager
    def _progress(self, *args, **kwargs):
        if self.progress:
            with log.progress(*args, **kwargs) as p:
                yield p
        else:
            with log.progress_log(*args, **kwargs) as p:
                yield p

    def build(self, task_list, influence=True):
        [self._get_node(task) for task in task_list]
        raise_error_if(not nx.is_directed_acyclic_graph(self.graph),
                       "there are cyclic task dependencies")
        self.graph._nodes_by_name = self.nodes

        if influence:
            with self._progress("Collecting task influence", len(self.graph.tasks), "tasks") as p:
                for node in reversed(list(nx.topological_sort(self.graph))):
                    node.finalize(self.graph, self.manifest)
                    p.update(1)

        return self.graph

    def display(self):
        from networkx.drawing.nx_agraph import write_dot

        t = tools.Tools()
        with t.tmpdir("dot") as tmpdir, t.cwd(tmpdir.get_path()):
            write_dot(self.graph, fs.path.join(t.getcwd(), 'graph.dot'))
            t.run('dot -Tsvg graph.dot -o graph.svg')
            t.run('eog graph.svg')
