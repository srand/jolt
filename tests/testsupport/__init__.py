#!/usr/bin/env python

from copy import copy, deepcopy
import os
import re

from jolt import *
from jolt import error
from jolt import filesystem as fs
from jolt.tasks import TaskRegistry
from jolt.plugins.allure import Test


def enable_network_testing(cls, storage_providers=None):
    if os.getenv("JOLT_NO_NETWORK_TESTS"):
        return cls
    class Gen(TaskGenerator):
        def generate(self):
            classes = []
            for provider in storage_providers or ["http"]:
                class Net(cls):
                    network = True
                    network_enabled = True
                    name = cls.name + "/" + provider
                    requires = ["jolt/amqp/deployment:storage=" + provider]
                    storage = provider

                    def __init__(self, *args, **kwargs):
                        super().__init__(*args, **kwargs)
                        self.network = True
                        self.network_enabled = True

                classes.append(Net)
            cls.requires = [c.name for c in classes]
            return classes + [cls]
    return Gen


def skip_if_no_deployment(method):
    def _wrap(self):
        if not self.network_enabled:
            self.skipTest("network build requirements not fulfilled")
        return method(self)
    return _wrap


def skip_if_network(method):
    def _wrap(self):
        if self.network:
            self.skipTest("network build not supported")
        return method(self)
    return _wrap


@influence.files("../../jolt/**/*.py")
class JoltTest(Test):
    abstract = True

    def __init__(self, *args, **kwargs):
        super(JoltTest, self).__init__(*args, **kwargs)
        self.network = False
        self.network_enabled = False

    def _files(self):
        if not self._testMethodDoc:
            return ""
        return re.findall(r"--- file: ([^\n]*)\n(.*?)(?=---)", self._testMethodDoc, re.M|re.DOTALL)

    def _recipe(self):
        if not self._testMethodDoc:
            return ""
        lines = "".join(re.findall(r"--- tasks:\n(.*?)---", self._testMethodDoc, re.M|re.DOTALL))
        return "\n".join([l[8:] for l in lines.splitlines()])

    def _config(self):
        if not self._testMethodDoc:
            return ""
        common = "\n[jolt]\ncachedir={}/cache\n".format(self.ws)
        lines = "".join(re.findall(r"--- config:\n(.*?)---", self._testMethodDoc, re.M|re.DOTALL))
        return common + "\n".join([l[8:] for l in lines.splitlines()])

    def _network_config(self):
        return self.deps["jolt/amqp/deployment:storage="+self.storage].strings.config.get_value() \
            if self.network_enabled else ""

    def setup(self, deps, tools):
        self.deps = deps
        self.ws = tools.builddir(self._testMethodName)
        with tools.cwd(self.ws):
            tools.setenv("JOLT_CONFIG_PATH", self.ws)
            tools.write_file("test.jolt", """
from jolt import *
from jolt.error import raise_error_if
from jolt.influence import global_string
global_string("{test}")
""".format(test=self._testMethodName) + self._recipe())
            tools.write_file("test.conf", self._config())
            tools.write_file("net.conf", self._network_config())

            for filename, content in self._files():
                content = "\n".join([l[8:] for l in content.splitlines()])
                dirname = fs.path.dirname(filename)
                if dirname:
                    print(dirname)
                    fs.makedirs(fs.path.join(self.ws, dirname))
                tools.write_file(filename, content)

    def cleanup(self):
        fs.rmtree(self.ws)

    def jolt(self, command, *args, **kwargs):
        with self.tools.cwd(self.ws):
            try:
                self._log = self.tools.run("jolt -c test.conf -c net.conf " + command.format(*args, **kwargs))
                return self._log
            except error.JoltCommandError as e:
                self._log = "\n".join(e.stdout + e.stderr)
                raise e

    def build(self, task, *args, **kwargs):
        network = "-n " if self.network else ""
        return self.jolt("-v build " + network + task, *args, **kwargs)

    def lastLog(self):
        return self._log

    def tasks(self, output, remote=False, local=False):
        if local:
            return re.findall("Execution started.*?\((.*) [^ ]*\)", output)
        if remote:
            return re.findall("Remote execution started.*?\((.*) [^ ]*\)", output)
        return re.findall("xecution started.*?\((.*) [^ ]*\)", output)

    def artifacts(self, output):
        return re.findall("Location: (.*)\n", output, re.M)

    def assertArtifact(self, r):
        artifacts = self.artifacts(r)
        if len(artifacts) <= 0:
            self.fail("no artifacts parsed from output")

        for artifact in artifacts:
            if not fs.path.exists(fs.path.join(self.ws, artifact)):
                self.fail("artifact {} doesn't exist".format(artifact))

    def assertNoArtifact(self, r):
        artifacts = self.artifacts(r)
        for artifact in artifacts:
            if fs.path.exists(fs.path.join(self.ws, artifact)):
                self.fail("artifact {} does exist".format(artifact))

    def assertBuild(self, r, task):
        tasks = self.tasks(r)
        if len(tasks) <= 0:
            self.fail("no tasks were executed")
        elif task not in tasks:
            self.fail("{} was not executed".format(task))

    def assertNoBuild(self, r, task=None):
        tasks = self.tasks(r)
        if (task is not None and task in tasks) or (task is None and len(tasks) > 0):
            self.fail("tasks were executed: {}".format(" ".join(tasks)))

    def assertDownload(self, r, task):
        tasks = re.findall("Download started.*?\((.*) [^ ]*\)", r)
        if len(tasks) <= 0:
            self.fail("no artifacts were downloaded")
        elif task not in tasks:
            self.fail("{} was not downloaded".format(task))

    def assertUpload(self, r, task):
        tasks = re.findall("Upload started.*?\((.*) [^ ]*\)", r)
        if len(tasks) <= 0:
            self.fail("no artifacts were downloaded")
        elif task not in tasks:
            self.fail("{} was not downloaded".format(task))

    def assertExists(self, *args):
        self.assertTrue(os.path.exists(fs.path.join(self.ws, *args)))

    def assertNotExists(self, *args):
        self.assertFalse(os.path.exists(fs.path.join(self.ws, *args)))
