

class JoltError(Exception):
    def __init__(self, *args, **kwargs):
        super(JoltError, self).__init__(*args, **kwargs)


class JoltCommandError(JoltError):
    def __init__(self, what, stdout, stderr, returncode, *args, **kwargs):
        super(JoltCommandError, self).__init__(what, *args, **kwargs)
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


def raise_error(msg, *args, **kwargs):
    raise JoltError(msg.format(*args, **kwargs))


def raise_task_error(task, msg, *args, **kwargs):
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
