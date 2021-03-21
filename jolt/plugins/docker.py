from jolt import *
from jolt import utils

from os import path


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

    compression = None
    """ Optional image compression "bz2", "gz", or "xz". """

    context = "."
    """ Path to build context, relative to joltdir (directory). """

    dockerfile = "Dockerfile"
    """ Path to the Dockerfile to build, or the full source code of such a file. """

    imagefile = None
    """ Name of the image tarball. Defaults to the task's canonical name. """

    tag = None
    """ Optional image tag. """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.imagefile = self.imagefile or utils.canonical(self.name) + ".tar"

    def run(self, deps, tools):
        context = tools.expand_relpath(self.context, self.joltdir)
        dockerfile = tools.expand_relpath(self.dockerfile, self.joltdir)
        tag = "-t " + self.tag if self.tag else ""

        if not path.exists(dockerfile):
            with tools.cwd(tools.builddir()):
                tools.write_file("Dockerfile", self.dockerfile)
                dockerfile = tools.expand_relpath("Dockerfile", self.joltdir)

        self.info("Building image from {} in {}", dockerfile, context)
        with tools.cwd(context):
            image = tools.run("docker build . -f {} --quiet {}", dockerfile, tag)

        try:
            self.info("Saving image to file")
            with tools.cwd(tools.builddir()):
                if self.tag:
                    tools.run("docker image save {} -o {imagefile}", self.tag)
                else:
                    tools.run("docker image save {} -o {imagefile}", image)
                if self.compression is not None:
                    tools.compress("{imagefile}", "{imagefile}.{compression}")
        finally:
            self.info("Removing image from Docker daemon")
            if tag:
                utils.call_and_catch(tools.run("docker image rm {tag}"))
            utils.call_and_catch(tools.run("docker image rm {}", image))

    def publish(self, artifact, tools):
        with tools.cwd(tools.builddir()):
            if self.compression is not None:
                artifact.collect("{imagefile}.{compression}")
            else:
                artifact.collect("{imagefile}")
