from jolt.tasks import Task, TaskRegistry
from jolt.cache import ArtifactCache
from jolt.graph import GraphBuilder
from jolt.error import raise_error_if
from jolt.manifest import JoltManifest
from jolt.scheduler import JoltEnvironment
from jolt.scheduler import LocalExecutor
from jolt.scheduler import LocalExecutorFactory
from jolt.scheduler import NetworkExecutorExtension
from jolt.scheduler import NetworkExecutorExtensionFactory
from jolt.loader import JoltLoader
from jolt import config
from jolt import filesystem as fs
from jolt import influence
from jolt import log
from jolt import utils


log.verbose("[SelfDeploy] Loaded")

_path = fs.path.dirname(__file__)
_path = fs.path.dirname(_path)
_path = fs.path.dirname(_path)


@influence.files(fs.path.join(_path, "**", "*.py"))
@influence.files(fs.path.join(_path, "**", "*.sh"))
@influence.files(fs.path.join(_path, "**", "*.xslt"))
@influence.files(fs.path.join(_path, "**", "*.template"))
class Jolt(Task):
    name = "jolt"

    def __init__(self, *args, **kwargs):
        super(Jolt, self).__init__(*args, **kwargs)
        self.influence.append(
            influence.StringInfluence(
                config.get("selfdeploy", "requires", "")))
        for e in self.extra_files:
            self.influence.append(influence.DirectoryInfluence(e))

    def _verify_influence(self, *args, **kwargs):
        pass  # FIXME: Validation doesn't work properly for directories

    @property
    def loaderdir(self):
        return JoltLoader.get().joltdir

    @property
    def extra_files(self):
        ext = config.get("selfdeploy", "extra", "")
        return [fs.path.join(self.loaderdir, e) for e in ext.split(",")] if ext else []

    @property
    def extra_dependencies(self):
        req = config.get("selfdeploy", "requires", "")
        return req.split() if req else []

    def info(self, fmt, *args, **kwargs):
        log.verbose(fmt, *args, **kwargs)

    @property
    def dependencies(self):
        """
        Queries local pip database for packages and versions used by jolt.

        The data is used to pin dependencies at specific versions so that
        the virtalenv installed on a worker matches what the client had
        installed locally.

        If pip is not available or its internal implementation has changed,
        no version pinning will be performed. Instead, workers will install
        Jolt with its default loose version requirements.
        """
        def get_installed_distributions():
            try:
                from pip._internal.metadata import get_environment
            except ImportError:
                from pip._internal.utils import misc
                return {
                    dist.project_name.lower(): dist
                    for dist in misc.get_installed_distributions()
                }
            else:
                dists = get_environment(None).iter_installed_distributions()
                return {dist._dist.project_name.lower(): dist._dist for dist in dists}

        dists = get_installed_distributions()
        reqs = ["jolt"] + [dep.lower() for dep in self.extra_dependencies]
        pkgs = {}

        while reqs:
            req = reqs.pop()

            dist = dists.get(req)
            if dist is None:
                self.info("[SelfDeploy] Dependency not found: {}", req)
                req = req.partition("=")[0].partition("<")[0].partition(">")[0]
                pkgs[req] = req
                continue

            for dep in dist.requires():
                name = dep.project_name.lower()
                if name not in pkgs:
                    reqs.append(name)

            pkgs[req] = f"{dist.project_name}=={dist.version}"

        del pkgs["jolt"]
        return pkgs.values()

    def publish(self, artifact, tools):
        with tools.cwd(tools.builddir()):
            try:
                pinned_reqs = self.dependencies
                if pinned_reqs:
                    tools.write_file("requirements.txt", "\n".join(pinned_reqs))
                    artifact.collect("requirements.txt")
            except Exception:
                log.exception()
        with tools.cwd(_path):
            artifact.collect('README.rst')
            artifact.collect('setup.py')
            artifact.collect('jolt/*.py')
            artifact.collect('jolt/*.sh')
            artifact.collect('jolt/*/*.py')
            artifact.collect('jolt/*/*/*.py')
            artifact.collect('jolt/*/*.xslt')
            artifact.collect('jolt/*/*.template')
            artifact.collect('jolt/plugins/selfdeploy/README.rst', flatten=True)
            artifact.collect('jolt/plugins/selfdeploy/setup.py', flatten=True)
            for e in self.extra_files:
                with tools.cwd(fs.path.dirname(e)):
                    artifact.collect(fs.path.basename(e))


class SelfDeployExtension(NetworkExecutorExtension):
    @utils.cached.instance
    def get_parameters(self, task):
        registry = TaskRegistry()
        registry.add_task_class(Jolt)
        acache = ArtifactCache.get()
        env = JoltEnvironment(cache=acache)
        gb = GraphBuilder(registry, JoltManifest())
        dag = gb.build(["jolt"])
        task = dag.select(lambda graph, task: True)
        assert len(task) == 1, "too many selfdeploy tasks found"
        task = task[0]
        if not acache.is_available_remotely(task):
            factory = LocalExecutorFactory()
            executor = LocalExecutor(factory, task, force_upload=True)
            executor.run(env)
        jolt_url = acache.location(task)
        raise_error_if(not jolt_url, "failed to deploy jolt to a remote cache")
        return {
            "jolt_url": jolt_url,
            "jolt_identity": task.identity[:8],
            "jolt_requires": config.get("selfdeploy", "requires", "")
        }


@NetworkExecutorExtensionFactory.Register
class SelfDeployExtensionFactory(NetworkExecutorExtensionFactory):
    def create(self):
        return SelfDeployExtension()
