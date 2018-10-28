import config
import keyring
import scheduler
import sys
from tps.jenkins import Jenkins
import log
import getpass
import inspect
import loader
import filesystem as fs
import hashlib
from jinja2 import Template
import utils

NAME = "jenkins"


@utils.Singleton
class JenkinsServer(object):
    def __init__(self):
        username, password = self._get_auth()
        self._server = Jenkins(config.get(NAME, "uri"), username, password)
        self.get_job_info = self._server.get_job_info
        self.get_build_info = self._server.get_build_info
        self.get_queue_item = self._server.get_queue_item
        self.build_job = self._server.build_job
        self._check_job()

    def _get_auth(self):
        service = config.get(NAME, "keyring.service")
        if not service:
            service = raw_input(NAME + " keyring service name (jenkins): ")
            if not service:
                service = NAME
            config.set(NAME, "keyring.service", service)
            config.save()

        username = config.get(NAME, "keyring.username")
        if not username:
            username = raw_input(NAME + " username: ")
            assert username, "no username configured for " + NAME
            config.set(NAME, "keyring.username", username)
            config.save()

        password = keyring.get_password(NAME, username)
        if not password:
            password = getpass.getpass(NAME + " password: ")
            assert password, "no password in keyring for " + NAME
            keyring.set_password(service, username, password)
        return username, password

    def _get_sha(self, data):
        sha = hashlib.sha1()
        sha.update(data)
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
        self.job_name = "{}-{}".format(config.get(NAME, "job", "Jolt"), template_sha[:6])

        try:
            job_xml = self._server.get_job_config(self.job_name)
        except:
            self._create_job(self.job_name, template_xml, self._server.create_job)
            return
        if self._get_sha(job_xml) != template_sha:
            assert self._create_job(
                self.job_name, template_xml, self._server.reconfig_job), \
                "[JENKINS] failed to change misconfigured job"

    def _create_job(self, name, job_template, func):
        template = Template(job_template)
        network_config = config.get("network", "config", "")
        xml = template.render(config=network_config)
        func(name, xml)
        return True


class JenkinsExecutor(scheduler.NetworkExecutor):
    def __init__(self, factory, cache, task):
        super(JenkinsExecutor, self).__init__(factory)
        self.server = JenkinsServer().get()
        self.cache = cache
        self.task = task
        self.job = self.server.job_name

    def run(self):
        self.task.started()

        task = [self.task.qualified_name]
        task += [t.qualified_name for t in self.task.extensions]
        
        parameters = {
            "joltfile": loader.JoltLoader.get().get_sources(),
            "task": " ".join(task),
            "task_identity": self.task.identity[:8]
        }
        parameters.update(scheduler.ExecutorRegistry.get().get_network_parameters(self.task))

        queue_id = self.server.build_job(self.job, parameters)
        log.verbose("[JENKINS] Queued {}", self.task.qualified_name)

        queue_info = self.server.get_queue_item(queue_id)
        while not queue_info.get("executable"):
            queue_info = self.server.get_queue_item(queue_id)
        
        log.verbose("[JENKINS] Executing {}", self.task.qualified_name)

        build_id = queue_info["executable"]["number"]

        build_info = self.server.get_build_info(self.job, build_id)
        while build_info["result"] not in ["SUCCESS", "FAILURE"]:
            build_info = self.server.get_build_info(self.job, build_id)

        log.verbose("[JENKINS] Finished {}", self.task.qualified_name)
        assert build_info["result"] == "SUCCESS", \
            "[JENKINS] {}: {}".format(build_info["result"], self.task.qualified_name)

        assert self.cache.is_available_remotely(self.task), \
            "[JENKINS] no artifact produced for {}, check configuration"\
            .format(self.task.qualified_name)

        assert self.cache.download(self.task), \
            "[JENKINS] failed to download artifact for {}"\
            .format(self.task.qualified_name)

        for extension in self.task.extensions:
            assert self.cache.download(extension), \
                "[JENKINS] failed to download artifact for {}"\
                .format(extension.qualified_name)
        
        return self.task


@scheduler.ExecutorFactory.Register
class JenkinsExecutorFactory(scheduler.NetworkExecutorFactory):
    def create(self, cache, task):
        return JenkinsExecutor(self, cache, task)

log.verbose("Jenkins loaded")
