from jolt import inspection
from jolt import utils


class JoltError(Exception):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


class JoltCommandError(JoltError):
    def __init__(self, what, stdout=[], stderr=[], returncode=None, *args, **kwargs):
        super().__init__(what, *args, **kwargs)
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


class JoltTimeoutError(JoltError):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def __str__(self):
        return super().__str__() or "Timeout"


class LoggedJoltError(JoltError):
    def __init__(self, exc):
        self.exc = exc


def raise_error(msg, *args, **kwargs):
    raise JoltError(msg.format(*args, **kwargs))


def raise_task_error(task, msg, *args, **kwargs):
    if task:
        with utils.ignore_exception():
            with task.report() as report:
                report.add_error(
                    kwargs.pop("type", "Error"),
                    inspection.getfile(task.__class__),
                    msg.format(*args, **kwargs))
        raise_error(msg + " (" + str(task) + ")", *args, **kwargs)
    else:
        raise_error(msg, *args, **kwargs)


def raise_unreported_task_error(task, msg, *args, **kwargs):
    if task:
        raise_error(msg + " (" + str(task) + ")", *args, **kwargs)
    else:
        raise_error(msg, *args, **kwargs)


def raise_error_if(condition, *args, **kwargs):
    if condition:
        raise_error(*args, **kwargs)


def raise_task_error_if(condition, task, *args, **kwargs):
    if condition:
        raise_task_error(task, *args, **kwargs)


def raise_unreported_task_error_if(condition, task, *args, **kwargs):
    if condition:
        raise_unreported_task_error(task, *args, **kwargs)


class raise_error_on_exception(object):
    def __init__(self, message):
        self.message = message

    def __enter__(self):
        return self

    def __exit__(self, type, value, tb):
        raise_error_if(value, self.message)


class raise_task_error_on_exception(object):
    def __init__(self, task, *args, **kwargs):
        self.task = task
        self.args = args
        self.kwargs = kwargs

    def __enter__(self):
        return self

    def __exit__(self, type, value, tb):
        raise_task_error_if(value, self.task, *self.args, **self.kwargs)
