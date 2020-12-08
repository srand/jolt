from jolt import config
from jolt import log
from jolt import tasks


log.verbose("[Alias] Loaded")


_registry = tasks.TaskRegistry.get()

for key, value in config.options("alias"):
    _registry.add_task_class(
        type("Alias", (tasks.Alias,), {
            "name": key,
            "requires": value.split(),
        })
    )
