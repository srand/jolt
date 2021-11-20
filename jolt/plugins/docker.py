from jolt import *
from jolt.error import raise_task_error_if
from jolt.tasks import TaskRegistry
from jolt import filesystem as fs
from jolt import utils

from jolt.cache import ArtifactListAttribute
from jolt.cache import ArtifactAttributeSet
from jolt.cache import ArtifactAttributeSetProvider

from functools import partial
from os import path
from platform import system



class DockerListVariable(ArtifactListAttribute):
    pass


class DockerLoadListVariable(DockerListVariable):
    def apply(self, task, artifact):
        for image in self.items():
            task.tools.run("docker load -i {}", fs.path.join(artifact.path, image))


class DockerPullListVariable(DockerListVariable):
    def apply(self, task, artifact):
        for image in self.items():
            task.tools.run("docker pull {}", image)


class DockerRmiListVariable(DockerListVariable):
    def unapply(self, task, artifact):
        for image in self.items():
            task.tools.run("docker rmi -f {}", image)



class DockerAttributeSet(ArtifactAttributeSet):
    def __init__(self, artifact):
        super(DockerAttributeSet, self).__init__()
        super(ArtifactAttributeSet, self).__setattr__("_artifact", artifact)

    def create(self, name):
        if name == "pull":
            return DockerPullListVariable(self._artifact, "pull")
        if name == "load":
            return DockerLoadListVariable(self._artifact, "load")
        if name == "rmi":
            return DockerRmiListVariable(self._artifact, "rmi")
        assert False, "no such docker attribute: {0}".format(name)


@ArtifactAttributeSetProvider.Register
class DockerAttributeProvider(ArtifactAttributeSetProvider):
    def create(self, artifact):
        setattr(artifact, "docker", DockerAttributeSet(artifact))

    def parse(self, artifact, content):
        if "docker" not in content:
            return
        for key, value in content["docker"].items():
            getattr(artifact.docker, key).set_value(value, expand=False)

    def format(self, artifact, content):
        if "docker" not in content:
            content["docker"] = {}
        for key, attrib in artifact.docker.items():
            content["docker"][key] = attrib.get_value()

    def apply(self, task, artifact):
        artifact.docker.apply(task, artifact)

    def unapply(self, task, artifact):
        artifact.docker.unapply(task, artifact)


class DockerClient(Download):
    """ Task: Downloads and publishes the Docker command line client.

    The task will be automatically made available after importing
    ``jolt.plugins.docker``.
    """

    name = "docker/cli"
    """ Name of the task """

    version = Parameter("20.10.9", help="Docker version")
    """ Docker version [20.10.9] """

    host = Parameter(system().lower(), help="Host operating system")
    """ Host operating system [autodetected] """

    arch = Parameter("x86_64", help="Host architecture")
    """ Host architecture [x86_64] """

    url = "https://download.docker.com/{host}/static/stable/{arch}/docker-{version}.tgz"
    """ URL of binaries """

    def publish(self, artifact, tools):
        with tools.cwd(self._builddir):
            artifact.collect("docker/docker")
        artifact.environ.PATH.append("docker")


class DockerLogin(Resource):
    """
    Resource: Logs in and out of a Docker Registry.

    If the user and password parameters are unset, credentials
    are fetched from the environment variables:

        - DOCKER_USER
        - DOCKER_PASSWD

    The resource will be automatically made available after importing
    ``jolt.plugins.docker``.
    """
    name = "docker/login"
    """ Name of the resource """

    requires = ["docker/cli"]

    user = Parameter("", help="Docker Registry username")
    """
    Docker Registry username.

    If not set, the environment variable ``DOCKER_USER`` is read instead.
    """

    passwd = Parameter("", help="Docker Registry password")
    """
    Docker Registry password.

    If not set, the environment variable ``DOCKER_PASSWD`` is read instead.
    """

    server = Parameter("", help="Docker Registry server")
    """
    Docker Registry server.

    If no server is specified, the default is defined by the daemon.
    """

    def _user(self, tools):
        return str(self.user) or tools.getenv("DOCKER_USER")

    def _password(self, tools):
        return str(self.passwd) or tools.getenv("DOCKER_PASSWD")

    def acquire(self, artifact, deps, tools):
        raise_task_error_if(not self._user(tools), self, "Username has not been configured")
        raise_task_error_if(not self._password(tools), self, "Password has not been configured")

        with tools.cwd(tools.builddir()):
            tools.write_file("docker-credential", self._password(tools))
            tools.run("cat docker-credential | docker login -u {user} --password-stdin {server}", user=self._user(tools))

    def release(self, artifact, deps, tools):
        tools.run("docker logout {server}")


TaskRegistry.get().add_task_class(DockerClient)
TaskRegistry.get().add_task_class(DockerLogin)


class DockerImage(Task):
    """
    Abstract Task: Builds and publishes a Docker image.

    Builds the selected ``Dockerfile`` and optionally tags and pushes the
    image to a registry. The image can also be saved to file and published
    in the task artifact. Compression formats supported are bzip2, gzip and
    lzma.

    By default, base images referenced in the ``Dockerfile`` will be pulled
    during the build. Note that Jolt has no way of knowing beforehand if
    images have been updated in the registry. Use time-based influence to
    trigger rebuilds if it's important that base images are kept up-to-date.

    No automatic influence for ``Dockerfile`` or context is collected. Make
    sure to use an appropriate influence decorator.

    Optionally add requirements to:

      - ``docker/cli`` to provision the Docker client, if none is available on the host.
      - ``docker/login`` to automatically login to the Docker registry.

    This class must be subclassed.

    Example:

    .. code-block:: docker

        # Dockerfile

        FROM busybox:latest
        CMD ["busybox"]

    .. code-block:: python

        # build.jolt

        from jolt.plugins.docker import DockerImage

        class Busybox(DockerImage):
            \"\"\" Publishes Busybox image as gzip-compressed tarball \"\"\"
            compression = "gz"
            requires = ["docker/cli"]
            tags = ["busybox:{identity}"]

    """
    abstract = True

    autoload = True
    """
    Automatically load image file into local registry when the artifact is
    consumed by another task.

    If the built image is saved to a file (i.e. ``imagefile`` is set), the image
    file is automatically loaded into the local Docker registry when the task
    artifact is consumed by another task. The image is also automatically
    removed from the registry upon completion of the consumer task.

    Default: ``True``.
    """

    buildargs = []
    """
    List of build arguments and their values ("ARG=VALUE").

    The arguments are passed to Docker using ``--build-arg``.
    """

    cleanup = True
    """ Remove image from Docker daemon upon completion [True] """

    compression = None
    """ Optional image compression "bz2", "gz", or "xz". """

    context = "."
    """ Path to build context, relative to joltdir (directory). """

    dockerfile = "Dockerfile"
    """ Path to the Dockerfile to build, or the full source code of such a file. """

    imagefile = "{canonical_name}.tar"
    """
    Name of the image tarball published by the task.

    If set to None, no image file will be saved and published.

    Defaults to the task's canonical name.
    """

    pull = True
    """
    Always pull images when building.

    Passes --pull to the Docker client.
    """

    push = False
    """
    Optionally push image to registry [False]

    To be able to push images, the current user must login to the Docker Registry.
    The ``docker/login`` Jolt resource can be used for that purpose.
    """

    tags = ["{canonical_name}:{identity}"]
    """ Optional list of image tags. Defaults to task's canonical name. """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def run(self, deps, tools):
        buildargs = " ".join(["--build-arg " + tools.expand(arg) for arg in self.buildargs])
        context = tools.expand_relpath(self.context, self.joltdir)
        dockerfile = tools.expand_path(self.dockerfile)
        self._imagefile = tools.expand(self.imagefile) if self.imagefile else None
        self._autoload = self._imagefile and self.autoload
        pull = " --pull" if self.pull else ""
        tags = [tools.expand(tag) for tag in self.tags]

        # If dockerfile is not relative to joltdir, look for it in context
        if not path.exists(dockerfile):
            with tools.cwd(context):
                dockerfile = tools.expand_path(self.dockerfile)

        if not path.exists(dockerfile):
            with tools.cwd(tools.builddir()):
                tools.write_file("Dockerfile", self.dockerfile)
                dockerfile = tools.expand_path("Dockerfile")

        self.info("Building image from {} in {}",
                  tools.expand_relpath(dockerfile),
                  tools.expand_relpath(context))

        with tools.cwd(context):
            image = tools.run("docker build . -f {} -t {} {}{}", dockerfile, tags[0], buildargs, pull)
            for tag in tags[1:]:
                tools.run("docker tag {} {}", tags[0], tag)

        try:
            if self.push:
                self.info("Pushing image")
                for tag in tags:
                    tools.run("docker push {}", tag)

            self.info("Saving image to file")
            with tools.cwd(tools.builddir()):
                if self._imagefile:
                    tools.run("docker image save {} -o {_imagefile}", tags[0])
                    if self.compression is not None:
                        tools.compress("{_imagefile}", "{_imagefile}.{compression}")
        finally:
            if self.cleanup:
                self.info("Removing image from Docker daemon")
                for tag in tags:
                    utils.call_and_catch(tools.run("docker image rm {}", tag))

    def publish(self, artifact, tools):
        artifact.strings.tag = tools.expand(self.tags[0])
        with tools.cwd(tools.builddir()):
            if self._imagefile:
                if self.compression is not None:
                    artifact.collect("{_imagefile}.{compression}")
                    if self._autoload:
                        artifact.docker.load.append("{_imagefile}.{compression}")
                else:
                    artifact.collect("{_imagefile}")
                    if self._autoload:
                        artifact.docker.load.append("{_imagefile}")
        if self._autoload:
            artifact.docker.rmi.append(artifact.strings.tag.get_value())

