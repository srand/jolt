from jolt import Alias
from jolt.pkgs import boringssl, libressl, openssl
from jolt.tasks import TaskRegistry


class VirtualSsl(Alias):
    name = "virtual/ssl"
    requires = ["openssl"]


TaskRegistry.get().add_task_class(VirtualSsl)
