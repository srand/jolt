from jolt import Parameter, Resource, Task
from jolt.error import raise_task_error_if
from jolt.tasks import TaskRegistry
from jolt import attributes
from jolt import config
from jolt import filesystem as fs
from jolt import log
from jolt import tools
from jolt import utils

from jolt.cache import ArtifactListAttribute
from jolt.cache import ArtifactAttributeSet
from jolt.cache import ArtifactAttributeSetProvider

import contextlib
import json
from os import path
import tarfile
import uuid


class PodmanListVariable(ArtifactListAttribute):
    pass


class PodmanImportListVariable(PodmanListVariable):
    def apply(self, task, artifact):
        for tar in self.items():
            try:
                tag = artifact.podman.tags[0]
            except IndexError:
                tag = artifact.tools.expand("{canonical_name}:{identity}")
            task.tools.run(
                "podman import {} {}",
                fs.path.join(artifact.path, tar), tag, output_on_error=True)
            for extra_tag in artifact.podman.tags[1:]:
                task.tools.run("podman tag {} {}", tag, extra_tag, output_on_error=True)


class PodmanLoadListVariable(PodmanListVariable):
    def apply(self, task, artifact):
        for image in self.items():
            task.tools.run(
                "podman load -i {}",
                fs.path.join(artifact.path, image), output_on_error=True)


class PodmanPullListVariable(PodmanListVariable):
    def apply(self, task, artifact):
        for image in self.items():
            task.tools.run("podman pull {}", image, output_on_error=True)


class PodmanRmiListVariable(PodmanListVariable):
    def unapply(self, task, artifact):
        for image in self.items():
            task.tools.run("podman rmi -f {}", image, output_on_error=True)


class PodmanAttributeSet(ArtifactAttributeSet):
    def __init__(self, artifact):
        super(PodmanAttributeSet, self).__init__()
        super(ArtifactAttributeSet, self).__setattr__("_artifact", artifact)

    def create(self, name):
        if name == "pull":
            return PodmanPullListVariable(self._artifact, "pull")
        if name == "load":
            return PodmanLoadListVariable(self._artifact, "load")
        if name == "imprt":
            return PodmanImportListVariable(self._artifact, "imprt")
        if name == "rmi":
            return PodmanRmiListVariable(self._artifact, "rmi")
        if name == "tags":
            return PodmanListVariable(self._artifact, "tags")
        assert False, "No such podman attribute: {0}".format(name)


@ArtifactAttributeSetProvider.Register
class PodmanAttributeProvider(ArtifactAttributeSetProvider):
    def create(self, artifact):
        setattr(artifact, "podman", PodmanAttributeSet(artifact))

    def parse(self, artifact, content):
        if "podman" not in content:
            return
        for key, value in content["podman"].items():
            getattr(artifact.podman, key).set_value(value, expand=False)

    def format(self, artifact, content):
        if "podman" not in content:
            content["podman"] = {}
        for key, attrib in artifact.podman.items():
            content["podman"][key] = attrib.get_value()

    def apply(self, task, artifact):
        artifact.podman.apply(task, artifact)

    def unapply(self, task, artifact):
        artifact.podman.unapply(task, artifact)


@attributes.requires("_image")
class Container(Resource):
    """
    Resource: Starts and stops a Podman container.
    """

    arguments = []
    """ Container argument list """

    cap_adds = []
    """ A list of capabilities to add to the container """

    cap_drops = []
    """ A list of capabilities to remove from the container """

    chroot = False
    """ Use as chroot - resource consumers will execute all commands in container """

    entrypoint = None
    """ Container entrypoint """

    environment = []
    """ Environment variables """

    image = None
    """
    Image tag or Jolt task.

    If a Jolt task is specified, its artifact must export a
    metadata string named ``tag`` with the name of the image tag.
    """

    labels = []
    """ A list of container metadata labels """

    privileged = False
    """
    Start container with elevated privileges.
    """

    ports = []
    """
    A list of container ports to publish.

    Example:

    .. code-block:: python

        ports = [
            "80",
            "443:443",
        ]

    Alternatively, assign ``True`` to publish all exposed ports to random ports.
    """

    release_on_error = True
    """ Stop and remove container on error to avoid resource leaks. """

    stop_timeout = 10
    """ Timeout in seconds for stopping the container .

    When stopping the container, the task will wait for the container to stop
    for the specified number of seconds before forcefully killing it.

    Default: 10 seconds.
    """

    volumes = []
    """
    A list of volumes to mount.

    By default, the cache directory and ``joltdir`` are automatically
    mounted in the container. See :attr:`volumes_default`.
    """

    volumes_default = [
        "{joltdir}",
        "{joltcachedir}",
    ]
    """
    A list of default volumes to mount.

    By default, the cache directory and ``joltdir`` are automatically
    mounted in the container. Override to disable.
    """

    user = None
    """
    Username or UID.

    Defaults to the current user.
    """

    @property
    def _arguments(self):
        return " ".join(self.arguments)

    @property
    def _cap_adds(self):
        return " ".join([utils.option("--cap-add ", cap) for cap in self.cap_adds])

    @property
    def _cap_drops(self):
        return " ".join([utils.option("--cap-drop ", cap) for cap in self.cap_drops])

    @property
    def _entrypoint(self):
        return utils.option("--entrypoint ", self.entrypoint)

    @property
    def _environment(self):
        return " ".join([utils.option("-e ", self.tools.expand(env)) for env in self.environment])

    @property
    def _image(self):
        registry = TaskRegistry.get()
        tool = tools.Tools(self)
        if registry.has_task(tool.expand(self.image)):
            return [self.image]
        return []

    def _info(self, fmt, *args, **kwargs):
        """
        Log information about the task.
        """
        fmt = self.tools.expand(fmt, *args, **kwargs)
        log.info(fmt, *args, **kwargs)

    @property
    def _labels(self):
        return " ".join([utils.option("-l ", self.tools.expand(label)) for label in self.labels])

    @property
    def _privileged(self):
        return "--privileged" if self.privileged else ""

    @property
    def _ports(self):
        if self.ports is True:
            return "-P"
        return " ".join([utils.option("-p ", self.tools.expand(port)) for port in self.ports])

    @property
    def _user(self):
        if self.user:
            return f"--user {self.user}"
        try:
            from os import getuid
            return "--user " + str(getuid())
        except ImportError:
            return ""

    @property
    def _volumes(self):
        return " ".join([utils.option("-v ", self.tools.expand_path(vol))
                         for vol in self.volumes_default + self.volumes])

    def acquire(self, artifact, deps, tools, owner):
        self._context_stack = None
        self.container = None
        self.joltcachedir = config.get_cachedir()
        try:
            image = deps[self.image]
            image = str(image.strings.tag)
        except Exception:
            image = tools.expand(self.image)

        self._info(f"Creating container from image '{image}'")
        with utils.delayed_interrupt():
            self.container = tools.run(
                "podman run -i -d {_cap_adds} {_cap_drops} {_entrypoint} {_labels} {_ports} {_privileged} {_user} {_environment} {_volumes} {image} {_arguments}",
                image=image, output_on_error=True)

        self._info("Created container '{container}'")
        info = tools.run("podman inspect {container}", output_on_error=True)
        artifact.container = self.container
        artifact.info = json.loads(info)[0]

        if self.chroot:
            self._context_stack = contextlib.ExitStack()
            self._context_stack.enter_context(
                owner.tools.runprefix(f"podman exec -i {artifact.container}"))

    def release(self, artifact, deps, tools, owner):
        if self.chroot and self._context_stack:
            self._context_stack.close()

        if not self.container:
            return

        try:
            self._info("Stopping container '{container}'")
            tools.run("podman stop -t {stop_timeout} {container}", output_on_error=True)
        finally:
            self._info("Deleting container '{container}'")
            tools.run("podman rm -f {container}", output_on_error=True)


class Compose(Resource):
    """
    Resource: Starts and stops the services of a Compose specification.

    The services are started with ``podman compose up`` when the resource is
    acquired and stopped and removed with ``podman compose down`` when it is
    released. Every acquisition uses a unique project name, so concurrent
    consumers get separate sets of containers, networks and volumes.

    ``podman compose`` runs an external Compose provider, either
    ``podman-compose`` or ``docker-compose`` (which requires the Podman API
    socket). Select it with the ``PODMAN_COMPOSE_PROVIDER`` environment variable
    or ``compose_providers`` in ``containers.conf``. Waiting for services
    requires ``podman-compose`` 1.4 or later.

    The artifact of the resource tells consumers about the started containers:

      - ``artifact.project`` is the Compose project name.
      - ``artifact.containers`` is a list of the ``podman inspect`` information
        of all containers in the project.
      - ``artifact.services`` maps service names to the ``podman inspect``
        information of the service's first container.

    No automatic influence for the Compose file is collected. Make sure to use
    an appropriate influence decorator, or write the specification inline.

    Example:

    .. code-block:: python

        from jolt.plugins.podman import Compose

        class Database(Compose):
            composefile = \"\"\"
            services:
              postgres:
                image: docker.io/library/postgres:17
                environment:
                  POSTGRES_PASSWORD: secret
                ports:
                  - "5432"
                healthcheck:
                  test: ["CMD", "pg_isready", "-U", "postgres"]
                  interval: 1s
            \"\"\"

        class IntegrationTest(Task):
            requires = ["database"]

            def run(self, deps, tools):
                db = deps["database"].services["postgres"]
                port = db["NetworkSettings"]["Ports"]["5432/tcp"][0]["HostPort"]
                ...

    """

    build = False
    """ Build images before starting the services (``--build``). """

    composefile = "compose.yaml"
    """
    Path to the Compose file, a list of such paths, or the full source code
    of a Compose specification.

    Paths are relative to ``joltdir``. Relative paths in the specification are
    resolved against the directory of the first Compose file, which for an
    inline specification is the build directory of the resource; use
    ``{joltdir}`` to refer to the workspace. A specification written inline is
    expanded like other task attributes, so literal braces must be doubled.
    """

    environment = []
    """
    A list of environment variables (``"NAME=VALUE"``) used for variable
    interpolation in the Compose specification.
    """

    profiles = []
    """ A list of Compose profiles to enable. """

    project = "{canonical_name}-{uuid}"
    """
    Compose project name.

    Only lowercase letters, digits, dashes and underscores are kept. The default
    is unique for every acquisition of the resource.
    """

    pull = None
    """ Image pull policy: ``"always"``, ``"missing"`` or ``"never"``. """

    release_on_error = True
    """ Stop and remove the services on error to avoid resource leaks. """

    remove_volumes = True
    """ Remove named and anonymous volumes of the project when released. """

    services = []
    """ A list of services to start. Starts all services if empty. """

    stop_timeout = 10
    """
    Timeout in seconds for stopping the containers.

    When stopping the services, Compose waits for the containers to stop for
    the specified number of seconds before forcefully killing them.

    Default: 10 seconds.
    """

    wait = True
    """
    Wait for the services to be running, or healthy if they have a
    healthcheck, before the consumer starts (``--wait``).
    """

    wait_timeout = None
    """ Timeout in seconds when waiting for services. """

    def _info(self, fmt, *args, **kwargs):
        fmt = self.tools.expand(fmt, *args, **kwargs)
        log.info(fmt, *args, **kwargs)

    def _composefiles(self, tools):
        files = self.composefile
        if isinstance(files, str):
            if "\n" in files:
                with tools.cwd(tools.builddir()):
                    tools.write_file("compose.yaml", files)
                    return [tools.expand_path("compose.yaml")]
            files = [files]
        return [tools.expand_path(f) for f in files]

    def _project_name(self, tools):
        name = tools.expand(self.project, uuid=uuid.uuid4().hex[:8]).lower()
        name = "".join([c if c.isalnum() or c in "-_" else "-" for c in name])
        return name.lstrip("-_")

    def _compose(self, tools):
        args = ["podman compose", f"-p {self.project_name}"]
        args += [utils.option("-f ", f) for f in self._composefiles(tools)]
        args += [utils.option("--profile ", tools.expand(p)) for p in self.profiles]
        return " ".join(filter(None, args))

    def _env(self, tools):
        env = {"PODMAN_COMPOSE_WARNING_LOGS": "false"}
        for var in self.environment:
            name, _, value = tools.expand(var).partition("=")
            env[name] = value
        return env

    def acquire(self, artifact, deps, tools, owner):
        self.project_name = self._project_name(tools)
        self._command = self._compose(tools)
        self._started = False

        options = ["up", "-d"]
        if self.build:
            options.append("--build")
        if self.pull:
            options.append(f"--pull {tools.expand(self.pull)}")
        if self.wait:
            options.append("--wait")
            if self.wait_timeout:
                options.append(f"--wait-timeout {self.wait_timeout}")
        options += [utils.quote(tools.expand(s)) for s in self.services]

        self._info("Starting Compose project '{project_name}'")
        with tools.environ(**self._env(tools)), utils.delayed_interrupt():
            self._started = True
            tools.run("{} {}", self._command, " ".join(options), output_on_error=True)

        artifact.project = self.project_name
        artifact.containers = []
        artifact.services = {}

        containers = tools.run(
            "podman ps -a -q --filter label=com.docker.compose.project={project_name}",
            output_on_error=True).split()
        if containers:
            info = tools.run("podman inspect {}", " ".join(containers), output_on_error=True)
            artifact.containers = json.loads(info)
        for container in artifact.containers:
            service = container["Config"]["Labels"].get("com.docker.compose.service")
            if service and service not in artifact.services:
                artifact.services[service] = container

        if self.wait:
            self._check_containers(artifact.containers)

    def _check_containers(self, containers):
        # podman-compose ignores errors when waiting for services
        for container in containers:
            state = container.get("State", {})
            name = container.get("Name", container.get("Id"))
            health = state.get("Health") or state.get("Healthcheck") or {}
            raise_task_error_if(
                state.get("Status") == "exited" and state.get("ExitCode", 0) != 0, self,
                "Container '{}' exited with code {}", name, state.get("ExitCode"))
            raise_task_error_if(
                health.get("Status") == "unhealthy", self,
                "Container '{}' is unhealthy", name)

    def release(self, artifact, deps, tools, owner):
        if not getattr(self, "_started", False):
            return

        options = ["down", "--remove-orphans", f"-t {self.stop_timeout}"]
        if self.remove_volumes:
            options.append("-v")

        self._info("Stopping Compose project '{project_name}'")
        with tools.environ(**self._env(tools)):
            tools.run("{} {}", self._command, " ".join(options), output_on_error=True)
        self._started = False


class PodmanLogin(Resource):
    """
    Resource: Logs in and out of a Podman Registry.

    If the user and password parameters are unset, credentials
    are fetched from the environment variables:

        - PODMAN_USER
        - PODMAN_PASSWD

    The resource will be automatically made available after importing
    ``jolt.plugins.podman``.
    """
    name = "podman/login"
    """ Name of the resource """

    user = Parameter("", help="Podman Registry username")
    """
    Podman Registry username.

    If not set, the environment variable ``PODMAN_USER`` is read instead.
    """

    passwd = Parameter("", help="Podman Registry password")
    """
    Podman Registry password.

    If not set, the environment variable ``PODMAN_PASSWD`` is read instead.
    """

    server = Parameter("", help="Podman Registry server")
    """
    Podman Registry server.

    If no server is specified, the default is defined by the daemon.
    """

    def _user(self, tools):
        return str(self.user) or tools.getenv("PODMAN_USER")

    def _password(self, tools):
        return str(self.passwd) or tools.getenv("PODMAN_PASSWD")

    def acquire(self, artifact, deps, tools, owner):
        raise_task_error_if(not self._user(tools), self, "Username has not been configured")
        raise_task_error_if(not self._password(tools), self, "Password has not been configured")

        with tools.cwd(tools.builddir()):
            tools.write_file("podman-credential", self._password(tools))
            tools.run("cat podman-credential | podman login -u {user} --password-stdin {server}", user=self._user(tools))

    def release(self, artifact, deps, tools, owner):
        tools.run("podman logout {server}")


TaskRegistry.get().add_task_class(PodmanLogin)


class _Tarfile(tarfile.TarFile):

    def without(self, targetpath):
        dirname, filename = fs.path.split(targetpath)
        if not filename.startswith(".wh."):
            return None
        fs.unlink(fs.path.join(dirname, filename[4:]), ignore_errors=True, tree=True)
        return True

    def makedev(self, tarinfo, targetpath):
        if self.without(targetpath):
            return
        super().makedev(tarinfo, targetpath)

    def makedir(self, tarinfo, targetpath):
        if self.without(targetpath):
            return
        super().makedir(tarinfo, targetpath)

    def makefifo(self, tarinfo, targetpath):
        if self.without(targetpath):
            return
        super().makefifo(tarinfo, targetpath)

    def makefile(self, tarinfo, targetpath):
        if self.without(targetpath):
            return
        if fs.path.lexists(targetpath):
            fs.unlink(targetpath)
        super().makefile(tarinfo, targetpath)

    def makelink(self, tarinfo, targetpath):
        if self.without(targetpath):
            return
        super().makelink(tarinfo, targetpath)


class ContainerImage(Task):
    """
    Abstract Task: Builds and publishes a Podman image.

    Builds the selected ``Dockerfile`` and optionally tags and pushes the
    image to a registry. The image can also be saved in the formats listed
    in :attr:`output` and published in the task artifact.

    By default, base images referenced in the ``Dockerfile`` will be pulled
    during the build. Note that Jolt has no way of knowing beforehand if
    images have been updated in the registry. Use time-based influence to
    trigger rebuilds if it's important that base images are kept up-to-date.

    No automatic influence for ``Dockerfile`` or context is collected. Make
    sure to use an appropriate influence decorator.

    Optionally add requirements to:

      - ``podman/login`` to automatically login to the Podman registry.

    This class must be subclassed.

    Example:

    .. code-block:: docker

        # Dockerfile

        FROM busybox:latest
        CMD ["busybox"]

    .. code-block:: python

        # build.jolt

        from jolt.plugins.podman import ContainerImage

        class Busybox(ContainerImage):
            \"\"\" Publishes Busybox image as an OCI archive \"\"\"
            output = ["oci-archive"]
            tags = ["busybox:{identity}"]

    """
    abstract = True

    annotations = []
    """ A list of image annotations """

    autoload = True
    """
    Automatically load image file into local registry when the artifact is
    consumed by another task.

    If the built image is saved to a file (i.e. ``imagefile`` is set), the image
    file is automatically loaded into the local Podman registry when the task
    artifact is consumed by another task. The image is also automatically
    removed from the registry upon completion of the consumer task.

    Default: ``True``.
    """

    buildargs = []
    """
    List of build arguments and their values ("ARG=VALUE").

    The arguments are passed to Podman using ``--build-arg``.
    """

    cleanup = True
    """ Remove local image upon completion [True] """

    context = "."
    """ Path to build context, relative to joltdir (directory). """

    dockerfile = "Dockerfile"
    """ Path to the Dockerfile to build, or the full source code of such a file. """

    output = ["oci-archive"]
    """
    List of output formats.

    If set to None, no output is produced and published.

    Supported formats:
        - archive
        - cpio
        - custom
        - directory
        - docker-archive
        - ext4
        - oci-archive
        - oci-directory
        - squashfs

    """

    imagefile = "{canonical_name}"
    """
    Name of the image tarball published by the task.

    If set to None, no image file will be saved and published.

    Defaults to the task's canonical name.
    """

    labels = []
    """ A list of image metadata labels """

    pull = True
    """
    Always pull images when building.

    Passes --pull to the Podman client.
    """

    push = False
    """
    Optionally push image to registry [False]

    To be able to push images, the current user must login to the Podman Registry.
    The ``podman/login`` Jolt resource can be used for that purpose.
    """

    size = None
    """ Size of the image, e.g. "64M" (for certain output formats). """

    squash = False
    """ Squash image layers """

    tags = ["{canonical_name}:{identity}"]
    """ Optional list of image tags. Defaults to task's canonical name. """

    target = None
    """ Target platform, e.g. linux/arm/v7. """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @property
    def _annotations(self):
        return " ".join([utils.option("--annotation ", self.tools.expand(an)) for an in self.annotations])

    @property
    def _buildargs(self):
        return " ".join([utils.option("--build-arg ", self.tools.expand(ba)) for ba in self.buildargs])

    @property
    def _labels(self):
        return " ".join([utils.option("-l ", self.tools.expand(label)) for label in self.labels])

    @property
    def _output(self):
        return utils.as_list(self.output) if self.output else []

    @property
    def _platform(self):
        platform = self.tools.expand(self.target) if self.target else None
        return utils.option("--platform ", platform)

    @property
    def _tags(self):
        return " ".join([utils.option("-t ", tag) for tag in self.tags])

    def run(self, deps, tools):
        context = tools.expand_relpath(self.context, self.joltdir)
        dockerfile = tools.expand_path(self.dockerfile)
        self._imagefile = tools.expand(self.imagefile) if self.imagefile else None
        self._autoload = self._imagefile and self.autoload
        self.tags = [self.tools.expand(tag) for tag in self.tags]
        pull = " --pull" if self.pull else ""
        squash = " --squash" if self.squash else ""

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
            tools.run("podman build {_platform} . -f {} {_annotations} {_buildargs} {_labels} {_tags} {pull}{squash}",
                      utils.quote(dockerfile), pull=pull, squash=squash)

        try:
            if self.push:
                self.info("Pushing image")
                for tag in self.tags:
                    tools.run("podman push {}", tag)

            for output in self._output:
                self.info("Saving image as {}", output)
                outdir = tools.builddir(output)
                with tools.cwd(outdir):
                    if output in ["oci-archive", "docker-archive"]:
                        tools.run("podman image save --format={output} {} -o {}", self.tags[0], "image.tar")
                    if output == "oci-directory":
                        tools.run("podman image save --format=oci-dir {} -o {}", self.tags[0], "image.dir")
                    if output in ["archive", "cpio", "custom", "directory", "ext4", "squashfs"]:
                        ctr = tools.run("podman create {}", self.tags[0])
                        try:
                            with tools.runprefix("podman unshare "):
                                mount_path = tools.run("podman mount {}", ctr, output_on_error=True)
                                if output == "custom":
                                    self.run_custom(deps, tools, mount_path)
                                elif output == "archive":
                                    tools.run("tar -C {} -cf image.tar .", mount_path, output_on_error=True)
                                elif output == "cpio":
                                    with tools.cwd(mount_path):
                                        tools.run("find | podman unshare cpio -o -F {}/image.cpio -H newc", outdir, output_on_error=True)
                                elif output == "ext4":
                                    assert self.size, "Size must be set for ext4 output"
                                    tools.run("mke2fs -t ext4 -F -L rootfs -d {} image.ext4 {size}", mount_path, output_on_error=True)
                                elif output == "squashfs":
                                    tools.run("mksquashfs {} image.squashfs", mount_path, output_on_error=True)
                                else:
                                    tools.mkdir("image.dir")
                                    tools.run("tar c -C {} . | tar --no-same-permissions --no-same-owner --no-overwrite-dir -x -C ./image.dir/", mount_path, output_on_error=True)
                        finally:
                            utils.call_and_catch(tools.run, "podman rm {}", ctr)
        finally:
            if self.cleanup:
                self.info("Removing image from Podman")
                for tag in self.tags:
                    utils.call_and_catch(tools.run("podman rmi -f {}", tag))

    def run_custom(self, deps, tools, mount_path):
        """
        Save image as custom output format.

        The method is called when the output format is set to "custom".
        The mount_path is the path to the mounted container root filesystem.

        The default implementation does nothing.
        """
        pass

    def publish(self, artifact, tools):
        """ Publish the image as different output formats """

        artifact.strings.tag = tools.expand(self.tags[0])

        for tag in self.tags:
            artifact.podman.tags.append(tag)

        for output in self._output:
            outdir = tools.builddir(output)
            with tools.cwd(outdir):
                if output in ["oci-archive", "docker-archive"] and self._imagefile:
                    artifact.collect("image.tar", output + "/{_imagefile}.tar")
                    if self._autoload:
                        artifact.podman.load.append(output + "/{_imagefile}.tar")
                        artifact.podman.rmi.append(artifact.strings.tag)
                if output in ["archive"] and self._imagefile:
                    artifact.collect("image.tar", output + "/{_imagefile}.tar")
                    if self._autoload:
                        artifact.podman.imprt.append(output + "/{_imagefile}.tar")
                        artifact.podman.rmi.append(artifact.strings.tag)
                if output in ["directory", "oci-directory"]:
                    with tools.cwd("image.dir"):
                        artifact.collect("*", f"{output}/", symlinks=True)
                if output in ["cpio"]:
                    artifact.collect("image.cpio", output + "/{_imagefile}.cpio")
                if output in ["custom"]:
                    self.publish_custom(artifact, tools)
                if output in ["directory"]:
                    artifact.paths.rootfs = output
                if output in ["ext4"]:
                    artifact.collect("image.ext4", output + "/{_imagefile}.ext4")
                if output in ["squashfs"]:
                    artifact.collect("image.squashfs", output + "/{_imagefile}.squashfs")

    def publish_custom(self, artifact, tools):
        """ Publish custom output as produced by run_custom """
        pass
