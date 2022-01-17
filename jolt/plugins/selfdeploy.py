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
        for e in self.extras:
            self.influence.append(influence.DirectoryInfluence(e))

    def _verify_influence(self, *args, **kwargs):
        pass  # FIXME: Validation doesn't work properly for directories

    @property
    def loaderdir(self):
        return JoltLoader.get().joltdir

    @property
    def extras(self):
        ext = config.get("selfdeploy", "extra", "")
        return [fs.path.join(self.loaderdir, e) for e in ext.split(",")] if ext else []

    def info(self, fmt, *args, **kwargs):
        log.verbose(fmt, *args, **kwargs)

    def publish(self, artifact, tools):
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
            for e in self.extras:
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
