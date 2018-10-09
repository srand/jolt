import config
import keyring
import scheduler
import sys
from tps.jenkins import Jenkins
import log
import getpass
import inspect
import loader

NAME = "jenkins"


class JenkinsExecutor(scheduler.Executor):
    def __init__(self, cache):
        super(JenkinsExecutor, self).__init__()
        self.cache = cache
        self.job = config.get(NAME, "job")
        username, password = self._get_auth()
        self.server = Jenkins(config.get(NAME, "uri"), username, password)

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

    def run(self, task):
        queue_id = self.server.build_job(self.job, {
            "buildfile": loader.JoltLoader.get().get_sources(),
            "task": task.qualified_name})

        log.info("[JENKINS] Queued {}", task.name)

        queue_info = self.server.get_queue_item(queue_id)
        while not queue_info.get("executable"):
            queue_info = self.server.get_queue_item(queue_id)
        
        log.info("[JENKINS] Executing {}", task.qualified_name)

        build_id = queue_info["executable"]["number"]
        
        build_info = self.server.get_build_info(self.job, build_id)
        while build_info["result"] not in ["SUCCESS", "FAILURE"]:
            build_info = self.server.get_build_info(self.job, build_id)

        log.info("[JENKINS] Executed {}: {}", task.name, build_info["result"])
        assert build_info["result"] == "SUCCESS", \
            "Execution failed: {}".format(task.name)

        assert self.cache.is_available_remotely(task), \
            "[JENKINS] no artifact produced for {}, check configuration".format(task.name)

        assert self.cache.download(task), \
            "[JENKINS] failed to download artifact for {}".format(task.name)


@scheduler.RegisterExecutor
class JenkinsExecutorFactory(object):
    def is_network(self):
        return True

    def is_eligable(self, cache, task):
        return True

    def create(self, cache):
        return JenkinsExecutor(cache)

log.verbose("Jenkins loaded")
