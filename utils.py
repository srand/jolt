import time


def as_list(t):
    return [t] if type(t) == str else list(t)

def as_stable_string_list(o):
    if type(o) == list or type(o) == tuple:
        return sorted([str(item) for item in o])
    elif type(o) == dict:
        return sorted(["{}={}".format(key, as_stable_string_list(val))
                       for key, val in o.itervalues()])
    else:
        return [str(o)]

def as_stable_tuple_list(o):
    assert type(o) == dict, "as_stable_tuple_list: argument is not a dict"
    l = [(key, value) for key, value in o.iteritems()]
    return sorted(l, key=lambda x: x[0])
    
def call_or_return(obj, t):
    return t(obj) if callable(t) else t

def parse_task_name(name):
    if ":" in name:
        task, params = name.split(":", 1)
        params = params.split(",")
        def _param(param):
            if "=" in param:
                key, value = param.split("=")
            else:
                key, value = param, None
            return key, value
        return task, {key: value for key, value in map(_param, params) if key}
    else:
        return name, {}

def format_task_name(name, params):
    if not params:
        return name
    def _param(key, value):
        return "{}={}".format(key, value) if value else key
    return "{}:{}".format(name, ",".join([_param(key, value) for key, value in params.iteritems()]))


def expand_macros(string, **kwargs):
    return string.format(**kwargs)


class duration(object):
    def __init__(self):
        self._time = time.time()

    def __str__(self):
        elapsed = time.time() - self._time
        if elapsed >= 60:
            return time.strftime("%Mmin %-Ss", time.gmtime(elapsed))
        return time.strftime("%-Ss", time.gmtime(elapsed))

class cached:
    @staticmethod
    def instance(f):
        def _f(self, *args, **kwargs):
            attr = "__cached_result_" + f.__name__
            if not hasattr(self, attr):
                setattr(self, attr, f(self, *args, **kwargs))
            return getattr(self, attr)
        return _f

def Singleton(cls):
    cls._instance = None
    @staticmethod
    def get():
        if not cls._instance:
            cls._instance = cls()
        return cls._instance
    cls.get = get
    return cls
