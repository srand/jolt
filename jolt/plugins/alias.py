from jolt import config
from jolt import log
from jolt import tasks


log.verbose("[Alias] Loaded")


_registry = tasks.TaskRegistry.get()

# Load task aliases from the configuration file
# and add them to the task registry.

for key, value in config.options("alias"):
    class ConfigAlias(tasks.Alias):
        name = key
        requires = value.split()
    _registry.add_task_class(ConfigAlias)
