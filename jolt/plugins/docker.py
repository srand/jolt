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

    cleanup = True
    """ Remove image from Docker daemon upon completion. Default: True """

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

    push = False
    """
    Optionally push image to registry. Default: False

    To be able to push images, the current user must login to the Docker Registry.
    The ``docker/login`` Jolt resource can be used for that purpose.
    """

    tags = ["{canonical_name}:{identity}"]
    """ Optional list of image tags. Defaults to task's canonical name. """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def run(self, deps, tools):
        context = tools.expand_relpath(self.context, self.joltdir)
        dockerfile = tools.expand(self.dockerfile)
        self._imagefile = tools.expand(self.imagefile) if self.imagefile else None
        tags = [tools.expand(tag) for tag in self.tags]

        if not path.exists(dockerfile):
            with tools.cwd(tools.builddir()):
                tools.write_file("Dockerfile", self.dockerfile)
                dockerfile = tools.expand_relpath("Dockerfile", self.joltdir)
        else:
            dockerfile = tools.expand_path(self.dockerfile)
            dockerfile = tools.expand_relpath(dockerfile, context)

        self.info("Building image from {} in {}", dockerfile, context)
        with tools.cwd(context):
            image = tools.run("docker build . -f {} -t {}", dockerfile, tags[0])
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
                else:
                    artifact.collect("{_imagefile}")
