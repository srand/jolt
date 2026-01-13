from jolt import Alias, BooleanParameter
from jolt.pkgs import boringssl, openssl
from jolt.tasks import TaskRegistry


class VirtualSsl(Alias):
    name = "virtual/ssl"
    shared = BooleanParameter(True, help="Use shared libraries.")
    requires = ["openssl:shared={shared}"]


TaskRegistry.get().add_task_class(VirtualSsl)
