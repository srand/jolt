import hashlib
import utils   
import inspect
from cache import *
from copy import copy


class Parameter(object):
    def __init__(self, default=None, help=None):
        self._default = default
        self._value = default
        self.__doc__ = help

    def __str__(self):
        return str(self._value)

    def get_default(self):
        return self._default

    def is_default(self):
        return self._default == self._value

    def is_unset(self):
        return self._value is None
    
    def get_value(self):
        return self._value

    def set_value(self, value):
        self._value = value


class TaskRegistry(object):
    _instance = None

    def __init__(self):
        self.classes = {}
        self.instances = {}
    
    @staticmethod
    def get():
        if not TaskRegistry._instance:
            TaskRegistry._instance = TaskRegistry()
        return TaskRegistry._instance

    def add_task_class(self, cls):
        self.classes[cls.name] = cls

    def get_task_class(self, name):
        return self.classes.get(name)

    def get_task_classes(self):
        return self.classes.values()
    
    def get_task(self, name, extra_params=None):
        name, params = utils.parse_task_name(name)
        params.update(extra_params or {})
        full_name = utils.format_task_name(name, params)

        task = self.instances.get(full_name)
        if task:
            return task

        cls = self.classes.get(name)
        if cls:
            task = cls()
            task._set_parameters(params)

            self.instances[full_name] = task
            return task

        assert task, "no such task: {}".format(full_name)

    
class Task(object):
    joltdir = "."

    classes = {}
    instances = {}

    attributes = []
    name = None
    requires = []
    extends = ""
    influence = []
        
    def __init__(self, name=None):
        super(Task, self).__init__()
        self.attributes = utils.as_list(self.__class__.attributes)
        self.influence = utils.as_list(self.__class__.influence)
        self.requires = utils.as_list(utils.call_or_return(self, self.__class__.requires))
        self.extends = utils.as_list(utils.call_or_return(self, self.__class__.extends))
        assert len(self.extends) == 1, "{} extends multiple tasks, only one allowed".format(self.name)
        self.extends = self.extends[0]
        self.name = self.__class__.name
        self._create_parameters()

        if name:
            self.name = name
        Task.instances[self.name] = self
        Task._create_parents(self.name)

    @staticmethod
    def _create_parents(name):
        names = name.split("/")

        if len(names) <= 1:
            return

        prev = None
        for i in reversed(range(0, len(names))):
            name = "/".join(names[:i + 1])
            task = Task.instances.get(name) or Task(name)
            if prev:
                task.requires += [prev.name]
            prev = task

    def _get_source(self, func):
        source, lines = inspect.getsourcelines(func)
        return "\n".join(source)

    def _get_source_functions(self):
        return [self.run, self.publish]

    def _get_source_hash(self):
        sha = hashlib.sha1()
        for func in self._get_source_functions():
            sha.update(self._get_source(func))
        return sha.hexdigest()

    def _get_requires(self):
        try:
            return [self._get_expansion(req) for req in self.requires]
        except KeyError as e:
            assert False, "invalid macro expansion used in task {}: {} - "\
                "forgot to set the parameter?".format(self.name, e)

    def _get_extends(self):
        try:
            return self._get_expansion(self.extends)
        except KeyError as e:
            assert False, "invalid macro expansion used in task {}: {} - "\
                "forgot to set the parameter?".format(self.name, e)

    def _get_expansion(self, string, *args, **kwargs):
        try:
            kwargs.update(**self._get_parameters())
            kwargs.update(**self._get_properties())
            return utils.expand_macros(string, *args, **kwargs)
        except KeyError as e:
            assert False, "invalid macro expansion used in task {}: {} - "\
                "forgot to set the parameter?".format(self.name, e)

    def _create_parameters(self):
        for key, param in self.__class__.__dict__.iteritems():
            if isinstance(param, Parameter):
                param = copy(param)
                setattr(self, key, param)
    
    def _set_parameters(self, params):
        for key, value in params.iteritems():
            param = self.__dict__.get(key)
            if isinstance(param, Parameter):
                param.set_value(value)
                continue
            assert False, "no such parameter for task {}: {}".format(self.name, key)
    
    def _get_parameters(self, unset=False):
        return {key: param.get_value()
                for key, param in self.__dict__.iteritems()
                if isinstance(param, Parameter) and \
                 (unset or not param.is_unset()) }

    def _get_properties(self):
        return {key: prop.__get__(self)
                for key, prop in self.__class__.__dict__.iteritems()
                if type(prop) == property }

    def is_cacheable(self):
        return True

    def is_runnable(self):
        return True

    def info(self, fmt, *args, **kwargs):
        log.info(fmt, *args, **kwargs)

    def error(self, fmt, *args, **kwargs):
        log.error(fmt, *args, **kwargs)

    def run(self, env, tools):
        pass

    def publish(self, artifact, tools):
        pass


class TaskTools(object):
    tmpdir = tools.tmpdir

    def __init__(self, node):
        self._node = node

    def cwd(self, path, *args, **kwargs):
        path = self._node.task._get_expansion(path, *args, **kwargs)
        return tools.cwd(path)

    def run(self, cmd, *args, **kwargs):
        cmd = self._node.task._get_expansion(cmd, *args, **kwargs)
        return tools.run(cmd, *args, **kwargs)

    def map_consecutive(self, callable, iterable):
        return utils.map_consecutive(callable, iterable)

    def map_concurrent(self, callable, iterable):
        return utils.map_concurrent(callable, iterable)


class Resource(Task):
    def __init__(self):
        super(Resource, self).__init__()

    def _get_source_functions(self):
        return super(Resource, self)._get_source_functions() + \
            [self.acquire, self.release]

    def is_cacheable(self):
        return False

    def is_runnable(self):
        return False

    def info(self, fmt, *args, **kwargs):
        pass

    def acquire(self, artifact, env, tools):
        pass

    def release(self, artifact, env, tools):
        pass

    def run(self, env, tools):
        self._run_env = env


@ArtifactAttributeSetProvider.Register
class ResourceAttributeSetProvider(ArtifactAttributeSetProvider):
    def create(self, artifact):
        pass

    def parse(self, artifact, content):
        pass

    def format(self, artifact, content):
        pass

    def apply(self, artifact):
        task = artifact.get_task()
        if isinstance(task, Resource):
            env = task._run_env
            env.__enter__()
            with tools.cwd(task.joltdir):
                task.acquire(artifact, env, TaskTools(task))

    def unapply(self, artifact):
        task = artifact.get_task()
        if isinstance(task, Resource):
            env = task._run_env
            with tools.cwd(task.joltdir):
                task.release(artifact, env, TaskTools(task))
            env.__exit__(None, None, None)
