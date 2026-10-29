from jolt import cli
from jolt import config
from jolt import log
from jolt import tools
from jolt.error import raise_error
from jolt.hooks import TaskHook, TaskHookFactory
from jolt.plugins.jobserver_main import launch_jobserver
from jolt.plugins.jobserver_main import find_jobserver
from jolt.plugins.jobserver_pressure import PressureMonitor, RESOURCES, parse_limits
from jolt.plugins.jobserver_pressure import DEFAULT_INTERVAL, DEFAULT_RAMP_TIME

import click


def _pressure_limits():
    """ Pressure limits from the configuration, validated. """
    limits = {
        resource: config.get("jobserver", "pressure_max_" + resource)
        for resource in RESOURCES
    }
    try:
        limits = parse_limits(limits)
    except ValueError as exc:
        raise_error("Invalid jobserver configuration: {}", exc)
    if limits and not PressureMonitor(limits).start():
        log.warning("Pressure information is unavailable, the jobserver will not limit pressure")
    return limits


@cli.cli.command(name="jobserver", hidden=True)
@click.argument("slots", type=int)
@click.option("--path", help="Directory that will contain the jobserver FIFO")
@click.pass_context
def jobserver_cmd(ctx, slots, path):
    """Launch a background jobserver and print environment variables to connect."""

    jobserver = launch_jobserver(
        slots, path=path, pressure=_pressure_limits(),
        interval=config.getfloat("jobserver", "pressure_interval", DEFAULT_INTERVAL),
        ramp_time=config.getfloat("jobserver", "ramp_time", DEFAULT_RAMP_TIME))

    env = jobserver.get_env()
    for key, value in env.items():
        print(f"{key}={value}")


# Launch the background jobserver helper process if configured to.
path = config.get("jobserver", "path")
if config.getboolean("jobserver", "launch", False):
    tools = tools.Tools()
    slots = config.getint("jobserver", "slots", tools.cpu_count())
    jobserver = launch_jobserver(
        slots, path=path, new_session=False, pressure=_pressure_limits(),
        interval=config.getfloat("jobserver", "pressure_interval", DEFAULT_INTERVAL),
        ramp_time=config.getfloat("jobserver", "ramp_time", DEFAULT_RAMP_TIME))
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
