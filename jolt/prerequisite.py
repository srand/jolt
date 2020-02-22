from jolt.tools import Tools
from jolt.error import JoltCommandError


class Prerequisite(object):
    def is_satisfied(self):
        raise NotImplementedError()


class CommandPrerequisite(Prerequisite):
    def __init__(self, command, wanted, func=lambda x, y: x in y):
        self._command = command
        self._wanted = wanted
        self._func = func

    def is_satisfied(self):
        t = Tools()
        try:
            output = t.run(self._command, output=False)
        except JoltCommandError as e:
            output = "".join(e.stdout + e.stderr)
        try:
            return self._func(self._wanted, output)
        except:
            return False

    def __str__(self):
        return "{}".format(self._wanted)


def command(*args, **kwargs):
    def _decorate(cls):
        _old_prereq = cls._prerequisites
        cmd = CommandPrerequisite(*args, **kwargs)
        def _prereq(self, *args, **kwargs):
            prereq = _old_prereq(self, *args, **kwargs)
            prereq.append(cmd)
            return prereq
        cls._prerequisites = _prereq
        return cls
    return _decorate
