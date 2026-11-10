from jolt import Download, Parameter, Resource, Task
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
from platform import system
import tarfile
import uuid


class DockerListVariable(ArtifactListAttribute):
    pass


class DockerLoadListVariable(DockerListVariable):
    def apply(self, task, artifact):
        for image in self.items():
            task.tools.run(
                "docker load -i {}",
                fs.path.join(artifact.path, image), output_on_error=True)


class DockerPullListVariable(DockerListVariable):
    def apply(self, task, artifact):
        for image in self.items():
            task.tools.run("docker pull {}", image, output_on_error=True)


class DockerRmiListVariable(DockerListVariable):
    def unapply(self, task, artifact):
        for image in self.items():
            task.tools.run("docker rmi -f {}", image, output_on_error=True)


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
        assert False, "No such docker attribute: {0}".format(name)


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

    arch = Parameter("x86_64", help="Host architecture")
    """ Host architecture [x86_64] """

    collect = ["docker/docker"]

    host = Parameter(system().lower(), help="Host operating system")
    """ Host operating system [autodetected] """

    url = "https://download.docker.com/{host}/static/stable/{arch}/docker-{version}.tgz"
    """ URL of binaries """

    version = Parameter("27.4.1", help="Docker version")
    """ Docker version [27.4.1] """

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.environ.PATH.append("docker")


@attributes.requires("_image")
class DockerContainer(Resource):
    """
    Resource: Starts and stops a Docker container.
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

    pid = None
    """ PID namespace to use. By default, the container is started with its own PID namespace.

    Set to "host" to use the host PID namespace.
    """

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

    security_opts = []
    """
    A list of security options.

    By default, the container is started with the default security profile.

    Example:

    .. code-block:: python

        security_opts = [
            "seccomp:unconfined",
        ]

    """

    stop_timeout = 10
    """ Timeout in seconds for stopping the container .

    When stopping the container, the task will wait for the container to stop
    for the specified number of seconds before forcefully killing it.

    Default: 10 seconds.
    """

    stop_signal = "SIGTERM"
    """ Signal to send to the container when stopping it.

    Default: ``SIGTERM``.
    """

    volumes = []
    """
    A list of volumes to mount.

    By default, the cache directory and ``joltdir`` are automatically
    mounted in the container. See :attr:`volumes_default`.
    """

    volumes_default = [
        "{joltdir}:{joltdir}",
        "{joltcachedir}:{joltcachedir}",
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

    workdir = None
    """ The container working directory. """

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
    def _pid(self):
        return f"--pid={self.pid}" if self.pid else ""

    @property
    def _privileged(self):
        return "--privileged" if self.privileged else ""

    @property
    def _ports(self):
        if self.ports is True:
            return "-P"
        return " ".join([utils.option("-p ", self.tools.expand(port)) for port in self.ports])

    @property
    def _security_opts(self):
        return " ".join([utils.option("--security-opt ", self.tools.expand(opt)) for opt in self.security_opts])

    @property
    def _stop_signal(self):
        return f" -s {self.stop_signal}" if self.stop_signal else ""

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
        return " ".join([utils.option("-v ", self.tools.expand(vol))
                         for vol in self.volumes_default + self.volumes])

    @property
    def _workdir(self):
        return "--workdir " + self.tools.expand(self.workdir) if self.workdir else ""

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
                "docker run -i -d {_cap_adds} {_cap_drops} {_entrypoint} {_labels} {_ports} {_privileged} {_security_opts} {_user} {_environment} {_volumes} {_workdir} {_pid} {image} {_arguments}",
                image=image, output_on_error=True)

        self._info("Created container '{container}'")
        info = tools.run("docker inspect {container}", output_on_error=True)
        artifact.container = self.container
        artifact.info = json.loads(info)[0]

        if self.chroot:
            self._context_stack = contextlib.ExitStack()
            self._context_stack.enter_context(
                owner.tools.runprefix(f"docker exec -i {artifact.container}"))

    def release(self, artifact, deps, tools, owner):
        if self.chroot and self._context_stack:
            self._context_stack.close()

        if not self.container:
            return

        try:
            self._info("Stopping container '{container}'")
            tools.run("docker stop{_stop_signal} -t {stop_timeout} {container}", output_on_error=True)
        finally:
            self._info("Deleting container '{container}'")
            tools.run("docker rm -f {container}", output_on_error=True)


class DockerCompose(Resource):
    """
    Resource: Starts and stops the services of a Docker Compose specification.

    The services are started with ``docker compose up`` when the resource is
    acquired and stopped and removed with ``docker compose down`` when it is
    released. Every acquisition uses a unique project name, so concurrent
    consumers get separate sets of containers, networks and volumes.

    The artifact of the resource tells consumers about the started containers:

      - ``artifact.project`` is the Compose project name.
      - ``artifact.containers`` is a list of the ``docker inspect`` information
        of all containers in the project.
      - ``artifact.services`` maps service names to the ``docker inspect``
        information of the service's first container.

    No automatic influence for the Compose file is collected. Make sure to use
    an appropriate influence decorator, or write the specification inline.

    Example:

    .. code-block:: python

        from jolt.plugins.docker import DockerCompose

        class Database(DockerCompose):
            composefile = \"\"\"
            services:
              postgres:
                image: postgres:17
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

    Paths are relative to ``joltdir``. A specification written inline is
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

    project_directory = None
    """
    Project directory that relative paths in the specification are resolved
    against.

    Defaults to the directory of the first Compose file, or ``joltdir`` if the
    specification is written inline.
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
                    return [tools.expand_path("compose.yaml")], True
            files = [files]
        return [tools.expand_path(f) for f in files], False

    def _project_name(self, tools):
        name = tools.expand(self.project, uuid=uuid.uuid4().hex[:8]).lower()
        name = "".join([c if c.isalnum() or c in "-_" else "-" for c in name])
        return name.lstrip("-_")

    def _compose(self, tools):
        files, inline = self._composefiles(tools)
        project_directory = self.project_directory
        if project_directory:
            project_directory = tools.expand_path(project_directory)
        elif inline:
            project_directory = self.joltdir

        args = ["docker compose", f"-p {self.project_name}"]
        args += [utils.option("-f ", f) for f in files]
        args += [utils.option("--project-directory ", project_directory)]
        args += [utils.option("--profile ", tools.expand(p)) for p in self.profiles]
        return " ".join(filter(None, args))

    def _env(self, tools):
        env = {}
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

        containers = tools.run("{} ps -a -q", self._command, output_on_error=True).split()
        if containers:
            info = tools.run("docker inspect {}", " ".join(containers), output_on_error=True)
            artifact.containers = json.loads(info)
        for container in artifact.containers:
            service = container["Config"]["Labels"].get("com.docker.compose.service")
            if service and service not in artifact.services:
                artifact.services[service] = container

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

    def acquire(self, artifact, deps, tools, owner):
        raise_task_error_if(not self._user(tools), self, "Username has not been configured")
        raise_task_error_if(not self._password(tools), self, "Password has not been configured")

        with tools.cwd(tools.builddir()):
            tools.write_file("docker-credential", self._password(tools))
            tools.run("cat docker-credential | docker login -u {user} --password-stdin {server}", user=self._user(tools))

    def release(self, artifact, deps, tools, owner):
        tools.run("docker logout {server}")


TaskRegistry.get().add_task_class(DockerClient)
TaskRegistry.get().add_task_class(DockerLogin)


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

    annotations = []
    """ A list of image annotations """

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

    extract = False
    """
    Extract image and publish rootfs tree.

    This option is useful when building a chroot to be used with
    :func:`jolt.Tools.chroot`. It disables saving of the image to a tarball.
    """

    imagefile = "{canonical_name}.tar"
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

    Passes --pull to the Docker client.
    """

    push = False
    """
    Optionally push image to registry [False]

    To be able to push images, the current user must login to the Docker Registry.
    The ``docker/login`` Jolt resource can be used for that purpose.
    """

    squash = False
    """ Squash image layers """

    tags = ["{canonical_name}:{identity}"]
    """ Optional list of image tags. Defaults to task's canonical name. """

    target = None
    """ Target platform, e.g. linux/arm/v7. """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def _extract_layer(self, tools, layerpath, targetpath):
        layerpath = tools.expand_path(layerpath)
        targetpath = tools.expand_path(targetpath)

        with _Tarfile.open(layerpath, 'r') as tar:
            tar.extractall(targetpath)

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
            tools.run("docker build {_platform} . -f {} {_annotations} {_buildargs} {_labels} {_tags} {pull}{squash}",
                      utils.quote(dockerfile), pull=pull, squash=squash)

        try:
            if self.push:
                self.info("Pushing image")
                for tag in self.tags:
                    tools.run("docker push {}", tag)

            if self._imagefile or self.extract:
                self.info("Saving image to file")
                with tools.cwd(tools.builddir()):
                    tools.run("docker image save {} -o {}", self.tags[0], self._imagefile or "image.tar")

            if self.extract:
                with tools.cwd(tools.builddir()):
                    tools.extract(self._imagefile or "image.tar", "layers/")
                    manifest = json.loads(tools.read_file("layers/manifest.json"))
                    for image in manifest:
                        for layer in image.get("Layers", []):
                            self.info("Extracting layer {}", fs.path.dirname(layer))
                            self._extract_layer(tools, fs.path.join("layers", layer), "rootfs/")
            elif self._imagefile:
                with tools.cwd(tools.builddir()):
                    if self.compression is not None:
                        tools.compress("{_imagefile}", "{_imagefile}.{compression}")

        finally:
            if self.cleanup:
                self.info("Removing image from Docker daemon")
                for tag in self.tags:
                    utils.call_and_catch(tools.run("docker image rm {}", tag))

    def publish(self, artifact, tools):
        artifact.strings.tag = tools.expand(self.tags[0])
        if self.extract:
            with tools.cwd(tools.builddir()):
                artifact.collect("rootfs", symlinks=True)
            artifact.paths.rootfs = "rootfs"
        elif self._imagefile:
            with tools.cwd(tools.builddir()):
                if self.compression is not None:
                    artifact.collect("{_imagefile}.{compression}")
                    if self._autoload:
                        artifact.docker.load.append("{_imagefile}.{compression}")
                else:
                    artifact.collect("{_imagefile}")
                    if self._autoload:
                        artifact.docker.load.append("{_imagefile}")
            if self._autoload:
                artifact.docker.rmi.append(artifact.strings.tag)
