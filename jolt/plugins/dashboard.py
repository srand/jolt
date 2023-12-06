from jolt import config
from jolt import error
from jolt import log
from jolt.hooks import TaskHookFactory
from jolt.plugins import telemetry


log.verbose("[Dashboard] Loaded")


class DashboardHooks(telemetry.TelemetryHooks):
    def __init__(self, uri=None):
        uri = config.get("dashboard", "uri", "http://dashboard.")
        error.raise_error_if(not uri, "dashboard.uri not configured")
        super().__init__(plugin="dashboard", uri=uri + "/api/v1/tasks", local=False)


# After logstash
@TaskHookFactory.register_with_prio(20)
class DashboardFactory(TaskHookFactory):
    def create(self, env):
        return DashboardHooks()
