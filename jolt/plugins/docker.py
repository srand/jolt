from jolt import *
from jolt.error import raise_task_error_if
from jolt.tasks import TaskRegistry
from jolt import utils

from functools import partial
from os import path
from platform import system


class DockerCLI(Download):
    """ Downloads and publishes the Docker command line client """
    name = "docker/cli"

    version = Parameter("20.10.9", help="Docker version")
    host = Parameter(system().lower(), help="Host operating system")
    arch = Parameter("x86_64", help="Host architecture")
    url = "https://download.docker.com/{host}/static/stable/{arch}/docker-{version}.tgz"

    def publish(self, artifact, tools):
        with tools.cwd(self._builddir):
            artifact.collect("docker/docker")
        artifact.environ.PATH.append("docker")


class DockerLogin(Resource):
    """
    Resource which logs in and out of a Docker Registry.

    If the user and password parameters are unset, credentials
    are fetched from the environment variables:

        - DOCKER_USER
        - DOCKER_PASSWD

    """
    name = "docker/login"

    requires = ["docker/cli"]

    user = Parameter("", help="Docker Registry username")
    passwd = Parameter("", help="Docker Registry password")

    def _user(self, tools):
        return str(self.user) or tools.getenv("DOCKER_USER")

    def _password(self, tools):
        return str(self.passwd) or tools.getenv("DOCKER_PASSWD")

    def acquire(self, artifact, deps, tools):
        raise_task_error_if(not self._user(tools), self, "Username has not been configured")
        raise_task_error_if(not self._password(tools), self, "Password has not been configured")

        with tools.cwd(tools.builddir()):
            tools.write_file("docker-credential", self._password(tools))
            tools.run("cat docker-credential | docker login -u {user} --password-stdin", user=self._user(tools))

    def release(self, artifact, deps, tools):
        tools.run("docker logout")


TaskRegistry.get().add_task_class(DockerCLI)
TaskRegistry.get().add_task_class(DockerLogin)


@influence.attribute("compression")
@influence.attribute("context")
@influence.attribute("dockerfile")
@influence.attribute("imagename")
@influence.attribute("tag")
class DockerImage(Task):
    """
    Builds a Docker image and publishes the resulting tarfile.

    The image may optionally be compressed using bzip2, gzip or lzma compression.

    Example:


    .. code-block:: python

        from jolt.plugins.docker import DockerImage

        class Busybox(DockerImage):
            compression = "gz"
            dockerfile = \"\"\"
            FROM busybox:latest
            CMD ["busybox"]
            \"\"\"
            tag = "busybox:latest"

    """
    abstract = True

    compression = None
    """ Optional image compression "bz2", "gz", or "xz". """

    context = "."
    """ Path to build context, relative to joltdir (directory). """

    dockerfile = "Dockerfile"
    """ Path to the Dockerfile to build, or the full source code of such a file. """

    imagefile = None
    """ Name of the image tarball. Defaults to the task's canonical name. """

    push = False
    """
    Optionally push image to registry. Default: False

    To be able to push images, the current user must login to the Docker Registry.
    The ``docker/login`` Jolt resource can be used for that purpose.
    """

    tag = "{canonical_name}:{identity}"
    """ Optional image tag. Defaults to task's canonical name. """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.imagefile = self.imagefile or utils.canonical(self.name) + ".tar"

    def run(self, deps, tools):
        context = tools.expand_relpath(self.context, self.joltdir)
        dockerfile = tools.expand(self.dockerfile)
        tag = tools.expand(self.tag)

        if not path.exists(dockerfile):
            with tools.cwd(tools.builddir()):
                tools.write_file("Dockerfile", self.dockerfile)
                dockerfile = tools.expand_relpath("Dockerfile", self.joltdir)
        else:
            dockerfile = tools.expand_path(self.dockerfile)
            dockerfile = tools.expand_relpath(dockerfile, context)

        self.info("Building image from {} in {}", dockerfile, context)
        with tools.cwd(context):
            image = tools.run("docker build . -f {} -t {}", dockerfile, tag)

        try:
            if self.push:
                self.info("Pushing image")
                tools.run("docker push {}", tag)

            self.info("Saving image to file")
            with tools.cwd(tools.builddir()):
                tools.run("docker image save {} -o {imagefile}", tag)
                if self.compression is not None:
                    tools.compress("{imagefile}", "{imagefile}.{compression}")
        finally:
            self.info("Removing image from Docker daemon")
            utils.call_and_catch(tools.run("docker image rm {}", tag))

    def publish(self, artifact, tools):
        artifact.strings.tag = tools.expand(self.tag)
        with tools.cwd(tools.builddir()):
            if self.compression is not None:
                artifact.collect("{imagefile}.{compression}")
            else:
                artifact.collect("{imagefile}")
