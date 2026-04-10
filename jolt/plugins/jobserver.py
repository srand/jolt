from jolt import cli
from jolt import config
from jolt import tools
from jolt.hooks import TaskHook, TaskHookFactory
from jolt.plugins.jobserver_main import launch_jobserver
from jolt.plugins.jobserver_main import find_jobserver

import click


@cli.cli.command(name="jobserver", hidden=True)
@click.argument("slots", type=int)
@click.option("--path", help="Directory that will contain the jobserver FIFO")
@click.pass_context
def jobserver_cmd(ctx, slots, path):
    """Launch a background jobserver and print environment variables to connect."""

    jobserver = launch_jobserver(slots, path=path)

    env = jobserver.get_env()
    for key, value in env.items():
        print(f"{key}={value}")


# Launch the background jobserver helper process if configured to.
path = config.get("jobserver", "path")
if config.getboolean("jobserver", "launch", False):
    tools = tools.Tools()
    slots = config.getint("jobserver", "slots", tools.cpu_count())
    jobserver = launch_jobserver(slots, path=path, new_session=False)
elif path:
    jobserver = find_jobserver(path=path)
else:
    jobserver = None


class JobserverTaskHooks(TaskHook):
    """ Task hooks to set environment variables for using the jobserver in tasks. """

    def __init__(self, jobserver):
        self._jobserver = jobserver

    def task_prerun(self, task, deps, tools):
        """Set environment variables to make tasks use the jobserver."""
        env = self._jobserver.get_env()
        for key, value in env.items():
            old_value = tools.getenv(key)
            if old_value:
                value = old_value + " " + value
            tools.setenv(key, value)


class JobserverTaskHookFactory(TaskHookFactory):
    def create(self, task):
        return JobserverTaskHooks(jobserver)


if jobserver:
    TaskHookFactory.register(JobserverTaskHookFactory)
