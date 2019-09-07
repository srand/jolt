import keyring
import getpass
import hashlib
from jinja2 import Template
import time
from requests.exceptions import ConnectionError, ReadTimeout
try:
    from StringIO import StringIO
except:
    from io import StringIO


from jolt import config
from jolt import utils
from jolt import scheduler
from jolt.tps.jenkins import Jenkins
from jolt import log
from jolt import filesystem as fs
from jolt.manifest import JoltManifest
from jolt.error import raise_error_if
from jolt.error import raise_task_error
from jolt.error import raise_task_error_if


NAME = "jenkins"
TYPE = "Remote execution"
TIMEOUT = (3.5, 27)
POLL_INTERVAL = 1


@utils.Singleton
class JenkinsServer(object):
    def __init__(self):
        username, password = self._get_auth()
        self._server = Jenkins(config.get(NAME, "uri"), username, password, timeout=TIMEOUT)
        self.get_job_info = self._server.get_job_info
        self.get_build_info = self._server.get_build_info
        self.get_build_console_output = self._server.get_build_console_output
        self.get_queue_item = self._server.get_queue_item
        self.build_job = self._server.build_job
        self.stop_build = self._server.stop_build
        self.cancel_queue = self._server.cancel_queue
        try:
            self._ok = self._check_job()
        except:
            log.exception()
            log.warning("[JENKINS] failed to establish server connection, disabled")
            self._ok = False

    def _get_auth(self):
        service = config.get(NAME, "keyring.service")
        if not service:
            service = utils.read_input(NAME + " keyring service name (jenkins): ")
            if not service:
                service = NAME
            config.set(NAME, "keyring.service", service)
            config.save()

        username = config.get(NAME, "keyring.username")
        if not username:
            username = utils.read_input(NAME + " username: ")
            raise_error_if(not username, "no username configured for " + NAME)
            config.set(NAME, "keyring.username", username)
            config.save()

        password = config.get(NAME, "keyring.password") or \
                   keyring.get_password(NAME, username)
        if not password:
            password = getpass.getpass(NAME + " password: ")
            raise_error_if(not password, "no password in keyring for " + NAME)
            keyring.set_password(service, username, password)
        return username, password

    def _get_sha(self, data):
        sha = hashlib.sha1()
        sha.update(data.encode())
        return sha.hexdigest()

    def _get_job_template_path(self):
        default = fs.path.join(fs.path.dirname(__file__), "jenkins.job")
        return config.get(NAME, "template", default)

    def _load_job_template(self):
        with open(self._get_job_template_path()) as f:
            xml = f.read()
        return xml, self._get_sha(xml)

    def _check_job(self):
        template_xml, template_sha = self._load_job_template()
        self.job_name = "{0}-{1}".format(
            config.get(NAME, "job", "Jolt"),
            template_sha[:6])

        try:
            job_xml = self._get_job_config(self.job_name)
        except:
            self._create_job(self.job_name, template_xml, self._server.create_job)
            view = config.get(NAME, "view")
            if view:
                self._add_job_to_view(view, self.job_name)
            return True
        if self._get_sha(job_xml) != template_sha:
            raise_error_if(
                not self._create_job(
                    self.job_name, template_xml, self._server.reconfig_job),
                "failed to update {0} job configuration", NAME)
        return True

    def ok(self):
        return self._ok

    @utils.retried.on_exception((ConnectionError, ReadTimeout))
    def _create_job(self, name, job_template, func):
        template = Template(job_template)
        network_config = config.get("network", "config", "", expand=False)
        xml = template.render(config=network_config)
        func(name, xml)
        return True

    @utils.retried.on_exception((ConnectionError, ReadTimeout))
    def _add_job_to_view(self, view, job):
        self._server.add_job_to_view(view, job)

    @utils.retried.on_exception((ConnectionError, ReadTimeout))
    def _get_job_config(self, job):
        return self._server.get_job_config(job)


class JenkinsExecutor(scheduler.NetworkExecutor):
    def __init__(self, factory, task):
        super(JenkinsExecutor, self).__init__(factory)
        self.server = JenkinsServer.get()
        self.factory = factory
        self.task = task
        self.job = self.server.job_name

    @utils.retried.on_exception((ConnectionError, ReadTimeout))
    def _get_queue_item(self, queue_id):
        return self.server.get_queue_item(queue_id)

    @utils.retried.on_exception((ConnectionError, ReadTimeout))
    def _get_build_info(self, build_id):
        return self.server.get_build_info(self.job, build_id)

    @utils.retried.on_exception((ConnectionError, ReadTimeout))
    def _build_job(self, parameters, files):
        return self.server.build_job(self.job, parameters, files=files)

    @utils.retried.on_exception((ConnectionError, ReadTimeout))
    def _cancel_queue(self, queue_id):
        return self.server.cancel_queue(queue_id)

    @utils.retried.on_exception((ConnectionError, ReadTimeout))
    def _stop_build(self, build_id):
        return self.server.stop_build(self.job, build_id)

    @utils.retried.on_exception((ConnectionError, ReadTimeout))
    def _get_console_log(self, build_id):
        if not config.getboolean(NAME, "console", True):
            return
        logtext = self.server.get_build_console_output(self.job, build_id)
        for line in logtext.splitlines():
            log.transfer(line, self.task.identity[:8])

    def _run(self, env):
        task = [self.task.qualified_name]
        task += [t.qualified_name for t in self.task.extensions]

        parameters = {
            "task": " ".join(task),
            "task_identity": self.task.identity[:8],
            "task_default": " ".join(["-d {0}".format(d) for d in self.factory.options.default])
        }
        registry = scheduler.ExecutorRegistry.get()
        parameters.update(registry.get_network_parameters(self.task))
        files = {}
        files["default.joltxmanifest"] = ("default.joltxmanifest", StringIO(JoltManifest.export(self.task).format()))

        raise_task_error_if(self.is_aborted(), self.task, "execution aborted by user")
        queue_id = self._build_job(parameters, files)

        log.verbose("[JENKINS] Queued {0}", self.task.qualified_name)

        queue_info = self._get_queue_item(queue_id)
        while not queue_info.get("executable"):
            raise_task_error_if(
                queue_info.get("cancelled"), self.task,
                "execution aborted by user")
            if self.is_aborted():
                self._cancel_queue(queue_id)
                raise_task_error(self.task, "execution aborted by user")
            time.sleep(POLL_INTERVAL)
            queue_info = self._get_queue_item(queue_id)

        log.verbose("[JENKINS] Executing {0}", self.task.qualified_name)

        self.task.running()
        for extension in self.task.extensions:
            extension.running()

        build_id = queue_info["executable"]["number"]
        build_info = self._get_build_info(build_id)
        abort_warning = False
        while build_info["result"] not in ["SUCCESS", "FAILURE", "ABORTED"]:
            if self.is_aborted() and not abort_warning:
                abort_warning = True
                log.verbose("[JENKINS] build aborted but '{0}' must run to completion",
                            self.task.qualified_name)
            time.sleep(POLL_INTERVAL)
            build_info = self._get_build_info(build_id)

        log.verbose("[JENKINS] Finished {0}", self.task.qualified_name)

        if build_info["result"] != "SUCCESS":
            self._get_console_log(build_id)

        raise_task_error_if(
            build_info["result"] != "SUCCESS", self.task,
            "Execution failed with status '{0}'", build_info["result"])

        raise_task_error_if(
            not env.cache.is_available_remotely(self.task), self.task,
            "no task artifact available in any cache, check configuration")

        raise_task_error_if(
            not env.cache.download(self.task) and env.cache.download_enabled(),
            self.task, "failed to download task artifact")

        for extension in self.task.extensions:
            raise_task_error_if(
                not env.cache.download(extension) and env.cache.download_enabled(),
                self.task, "failed to download task artifact")

        return self.task

    def run(self, env):
        try:
            self.task.started(TYPE)
            for extension in self.task.extensions:
                extension.started(TYPE)
            self._run(env)
            for extension in self.task.extensions:
                extension.finished(TYPE)
            self.task.finished(TYPE)
        except Exception as e:
            log.exception()
            for extension in self.task.extensions:
                extension.failed(TYPE)
            self.task.failed(TYPE)
            raise e
        return self.task


@scheduler.ExecutorFactory.Register
class JenkinsExecutorFactory(scheduler.NetworkExecutorFactory):
    def __init__(self, options):
        workers = config.getint(NAME, "workers", 16)
        super(JenkinsExecutorFactory, self).__init__(max_workers=workers)
        self._options = options

    @property
    def options(self):
        return self._options

    def create(self, task):
        server = JenkinsServer.get()
        if not server.ok():
            return None
        return JenkinsExecutor(self, task)

log.verbose("[Jenkins] Loaded")
