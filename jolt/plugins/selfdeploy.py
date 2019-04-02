from jolt.tasks import *
from jolt.plugins import directory
from jolt.cache import *
from jolt.graph import *
from jolt.scheduler import *
from jolt.loader import JoltLoader
from jolt import config

log.verbose("SelfDeploy loaded")


_path = fs.path.dirname(__file__)
_path = fs.path.dirname(_path)
_path = fs.path.dirname(_path)


@directory.influence(_path, pattern="*.py")
class Jolt(Task):
    name = "jolt"

    def __init__(self, *args, **kwargs):
        super(Jolt, self).__init__(*args, **kwargs)
        with Tools(self) as tools:
            for e in self.extras:
                self.influence.append(directory.DirectoryInfluenceProvider(e, pattern='*.py'))

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
            artifact.collect('jolt/*.job')
            artifact.collect('jolt/*/*.py')
            artifact.collect('jolt/*/*/*.py')
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
            duration = utils.duration()
            factory = LocalExecutorFactory()
            executor = LocalExecutor(factory, task, force_upload=True)
            executor.run(env)
        jolt_url = acache.location(task)
        assert jolt_url, "failed to selfdeploy jolt to remote cache"
        return { "jolt_url":  jolt_url, "jolt_identity": task.identity[:8] }


@NetworkExecutorExtensionFactory.Register
class SelfDeployExtensionFactory(NetworkExecutorExtensionFactory):
    def create(self):
        return SelfDeployExtension()
