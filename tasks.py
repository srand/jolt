import hashlib
import utils   
import inspect
from copy import copy


class Parameter(object):
    def __init__(self, default=None):
        self._default = default
        self._value = default

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
    classes = {}
    instances = {}

    attributes = []
    name = None
    requires = []
    influence = []
        
    def __init__(self, name=None):
        super(Task, self).__init__()
        self.attributes = utils.as_list(self.__class__.attributes)
        self.requires = utils.as_list(utils.call_or_return(self, self.__class__.requires))
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
            
    def _get_source_hash(self):
        sha = hashlib.sha1()
        sha.update(self._get_source(self.run))
        sha.update(self._get_source(self.publish))
        return sha.hexdigest()

    def _get_requires(self):
        try:
            return [utils.expand_macros(req, **self._get_parameters()) for req in self.requires]
        except KeyError as e:
            assert False, "invalid macro expansion used in task {}: {} - "\
                "forgot to set the parameter?".format(self.name, e)

    def _get_expansion(self, string):
        try:
            return utils.expand_macros(string, **self._get_parameters())
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

    def run(self, env, tools):
        pass

    def publish(self, artifact):
        pass
