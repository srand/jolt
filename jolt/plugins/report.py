from contextlib import contextmanager

from jolt import common_pb2 as common_pb
from jolt.hooks import TaskHook, TaskHookFactory
from jolt.manifest import JoltManifest


class ReportHooks(TaskHook):
    def __init__(self):
        self.manifest = JoltManifest()

    def finalize_report(self, report, task, result):
        report.name = task.qualified_name
        report.goal = str(task.is_goal()).lower()
        report.identity = task.identity
        report.instance = task.instance
        report.result = result
        if task.duration_running:
            report.duration = str(task.duration_running.seconds)
        if hasattr(task, "logstash"):
            report.logstash = task.logstash
        self.manifest.append(report)

    def task_skipped(self, task):
        if task.is_goal():
            with task.task.report() as report:
                self.finalize_report(report.manifest, task, "SKIPPED")

    def task_finished_download(self, task):
        if task.is_goal():
            with task.task.report() as report:
                self.finalize_report(report.manifest, task, "DOWNLOADED")

    def task_finished_upload(self, task):
        if task.is_goal():
            with task.task.report() as report:
                self.finalize_report(report.manifest, task, "UPLOADED")

    def task_failed(self, task):
        with task.task.report() as report:
            if task.status() == common_pb.TaskStatus.TASK_FAILED:
                self.finalize_report(report.manifest, task, "FAILED")
            elif task.status() == common_pb.TaskStatus.TASK_CANCELLED:
                self.finalize_report(report.manifest, task, "CANCELLED")

    def task_unstable(self, task):
        with task.task.report() as report:
            self.finalize_report(report.manifest, task, "UNSTABLE")

    @contextmanager
    def task_run(self, task):
        try:
            yield
        except Exception as e:
            with task.task.report() as report:
                if not report.errors:
                    report.add_exception(e)
            raise e
        else:
            with task.task.report() as report:
                if task.status() == common_pb.TaskStatus.TASK_PASSED:
                    self.finalize_report(report.manifest, task, "SUCCESS")

    def write(self, filename):
        self.manifest.write(filename)

    @contextmanager
    def update(self):
        yield self.manifest


_report_hooks = ReportHooks()


def update():
    return _report_hooks.update()


def write(filename):
    return _report_hooks.write(filename)


@TaskHookFactory.register_with_prio(-10)
class ReportFactory(TaskHookFactory):
    def create(self, env):
        return _report_hooks
