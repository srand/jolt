from tasks import *
from plugins import directory
from cache import *
from graph import *
from scheduler import *


log.verbose("SelfDeploy loaded")


_path = fs.path.dirname(__file__)
_path = fs.path.dirname(_path)


@directory.influence(_path, pattern="*.py")
class Jolt(Task):
    name = "jolt"

    def info(self, fmt, *args, **kwargs):
        log.verbose(fmt, *args, **kwargs)

    def publish(self, artifact, tools):
        with tools.cwd(_path):
            artifact.collect('README.rst')
            artifact.collect('*.py')
            artifact.collect('*/*.py')
            artifact.collect('*/*.job')
            artifact.collect('*/*/*.py')
        

class SelfDeployExtension(NetworkExecutorExtension):
    @utils.cached.instance
    def get_parameters(self, task):
        acache = ArtifactCache()
        task = TaskProxy(Jolt())
        task.identity
        if not acache.is_available_remotely(task):
            duration = utils.duration()
            try:
                factory = LocalExecutorFactory()
                task.info("Execution started")
                executor = LocalExecutor(factory, acache, task, force_upload=True)
                executor.run()
                task.info("Execution finished after {}", duration)
            except:
                task.error("Execution failed after {}", duration)
                raise
        jolt_url = acache.location(task)
        assert jolt_url, "failed to selfdeploy jolt to remote cache"
        return { "jolt_url":  jolt_url}


@NetworkExecutorExtensionFactory.Register
class SelfDeployExtensionFactory(NetworkExecutorExtensionFactory):
    def create(self):
        return SelfDeployExtension()
