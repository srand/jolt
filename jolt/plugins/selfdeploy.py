import os
import pkg_resources

from jolt import config
from jolt import filesystem as fs
from jolt import influence
from jolt import log
from jolt import common_pb2 as common_pb
from jolt import utils
from jolt import version
from jolt.cache import ArtifactCache
from jolt.error import raise_error_if
from jolt.graph import GraphBuilder
from jolt.loader import JoltLoader
from jolt.manifest import JoltManifest
from jolt.scheduler import JoltEnvironment
from jolt.scheduler import LocalExecutor
from jolt.scheduler import LocalExecutorFactory
from jolt.scheduler import NetworkExecutorExtension
from jolt.scheduler import NetworkExecutorExtensionFactory
from jolt.tasks import Task, TaskRegistry


log.verbose("[SelfDeploy] Loaded")

_path = fs.path.dirname(__file__)
_path = fs.path.dirname(_path)
_path = fs.path.dirname(_path)


@influence.files(fs.path.join(_path, "**", "*.py"))
@influence.files(fs.path.join(_path, "**", "*.sh"))
@influence.files(fs.path.join(_path, "**", "*.xslt"))
@influence.files(fs.path.join(_path, "**", "*.template"))
@influence.attribute("dependencies")
@influence.attribute("extra_dependencies")
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
        return get_extra_dependencies()

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
        return get_dependencies(["jolt"] + self.extra_dependencies)

    def publish(self, artifact, tools):
        with tools.cwd(tools.builddir()):
            pinned_reqs = self.dependencies
            if pinned_reqs:
                tools.write_file("requirements.txt", "\n".join(pinned_reqs))
                artifact.collect("requirements.txt")
        with tools.cwd(_path):
            artifact.collect('README.rst')
            artifact.collect('setup.py')
            artifact.collect('jolt/*.py')
            artifact.collect('jolt/*.sh')
            artifact.collect('jolt/*/*.py')
            artifact.collect('jolt/*/*/*.py')
            artifact.collect('jolt/*/*.xslt')
            artifact.collect('jolt/*/*.template')
            artifact.collect('jolt/bin')
            artifact.collect('jolt/plugins/selfdeploy/README.rst', flatten=True)
            artifact.collect('jolt/plugins/selfdeploy/setup.py', flatten=True)
            for e in self.extra_files:
                with tools.cwd(fs.path.dirname(e)):
                    artifact.collect(fs.path.basename(e))


class SelfDeployExtension(NetworkExecutorExtension):
    @utils.cached.instance
    def get_parameters(self, _):
        client = get_client()
        params = {}
        if client.identity:
            params["jolt_identity"] = client.identity
        if client.url:
            params["jolt_url"] = client.url
        return params


@NetworkExecutorExtensionFactory.Register
class SelfDeployExtensionFactory(NetworkExecutorExtensionFactory):
    def create(self):
        return SelfDeployExtension()


@utils.cached.method
def get_dependencies(packages=None):
    reqs = packages or ["jolt"]
    pkgs = {}

    while reqs:
        req = reqs.pop()

        dist = pkg_resources.working_set.by_key.get(req)
        if dist is None:
            log.debug("[SelfDeploy] Dependency not found: {}", req)
            pkgs[req] = req
            continue

        for dep in dist.requires():
            if dep.name not in pkgs:
                reqs.append(dep.name)

        pkgs[req] = f"{dist.project_name}=={dist.version}"

    try:
        del pkgs["jolt"]
    except KeyError:
        pass

    return list(sorted(pkgs.values()))


@utils.cached.method
def get_extra_dependencies():
    req = config.get("selfdeploy", "requires", "")
    return req.split() if req else []


@utils.cached.method
def publish_artifact():
    registry = TaskRegistry()
    registry.add_task_class(Jolt)
    acache = ArtifactCache.get()
    env = JoltEnvironment(cache=acache)
    gb = GraphBuilder(registry, acache, JoltManifest())
    dag = gb.build(["jolt"])
    task = dag.select(lambda graph, task: True)
    assert len(task) == 1, "Too many selfdeploy tasks found"
    task = task[0]
    if not task.is_available_remotely(cache=False):
        factory = LocalExecutorFactory()
        executor = LocalExecutor(factory, task, force_upload=True)
        executor.run(env)
    jolt_url = acache.location(task.artifacts[0])
    raise_error_if(not jolt_url, "Failed to deploy jolt to a remote cache")
    cacheUrl = config.get("http", "uri", config.get("cache", "uri", "") + "/files")
    substituteUrl = config.get("selfdeploy", "baseUri")
    if cacheUrl and substituteUrl:
        return task.identity, jolt_url.replace(cacheUrl, substituteUrl)
    return task.identity, jolt_url


def get_floating_version():
    identity, url = publish_artifact()
    return common_pb.Client(
        identity=identity,
        url=url,
        version=version.__version__,
    )


def get_pinned_version():
    return common_pb.Client(
        requirements=get_extra_dependencies(),
        version=version.__version__,
    )


def get_nix_version():
    return common_pb.Client(
        requirements=get_extra_dependencies(),
        version=version.__version__,
        nix=True,
    )


def get_client():
    # Floating version is a special case where we want to deploy the Jolt
    # source code to a remote cache and use that URL as the client URL
    # for workers.
    floating = config.getboolean("selfdeploy", "floating", False)
    if floating:
        return get_floating_version()

    # If Nix has been explicitly disabled, we want to pin versions.
    if not config.getboolean("selfdeploy", "nix", True):
        return get_pinned_version()

    # If Nix has been explicitly enabled, we want to use the Nix shell.
    if config.getboolean("selfdeploy", "nix", False):
        return get_nix_version()

    # If we are in a Nix shell, we want to use the Nix shell.
    if os.environ.get("IN_NIX_SHELL"):
        return get_nix_version()

    # Default to pinned version
    return get_pinned_version()
