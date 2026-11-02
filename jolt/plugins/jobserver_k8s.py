"""Kubernetes device plugin for the CUSE jobserver.

Advertises the jobserver device node to the kubelet as an extended resource.
Pods that request the resource are only started on a node once the device
node exists, and the container runtime adds the device to their containers.

The kubelet removes the sockets of all plugins when it restarts, and the
plugin then registers again.
"""

from __future__ import annotations

import os
import sys
import threading
from concurrent import futures
from typing import Optional

import grpc

from jolt.plugins import deviceplugin_pb2 as api
from jolt.plugins import deviceplugin_pb2_grpc as api_grpc


API_VERSION = "v1beta1"
DEVICE_PLUGIN_PATH = "/var/lib/kubelet/device-plugins"
KUBELET_SOCKET = "kubelet.sock"
# The default maximum number of pods on a node
DEFAULT_DEVICES = 110
RETRY_INTERVAL = 5.0


def log(message: str, *args: object) -> None:
    if args:
        message = message % args
    print(message, file=sys.stderr, end="")


class DevicePlugin(api_grpc.DevicePluginServicer):
    """
    Advertises a device node as a number of devices, each of which a
    container can be allocated. All of them are the same device node,
    which containers share.
    """

    def __init__(
        self,
        resource: str,
        path: str,
        devices: int = DEFAULT_DEVICES,
        plugin_path: str = DEVICE_PLUGIN_PATH,
        retry_interval: float = RETRY_INTERVAL,
    ) -> None:
        if devices < 1:
            raise ValueError("the number of devices must be a positive integer")
        self.resource = resource
        self.path = path
        self.devices = devices
        self.plugin_path = plugin_path
        self.retry_interval = retry_interval
        self.endpoint = resource.replace("/", "-") + ".sock"
        self.socket = os.path.join(plugin_path, self.endpoint)
        self.stop = threading.Event()
        self.server: Optional[grpc.Server] = None

    def GetDevicePluginOptions(self, request, context):
        return api.DevicePluginOptions()

    def ListAndWatch(self, request, context):
        # The device node exists before the plugin starts, and the devices
        # stay healthy for as long as the jobserver runs.
        name = os.path.basename(self.path)
        yield api.ListAndWatchResponse(devices=[
            api.Device(ID=f"{name}-{i}", health="Healthy")
            for i in range(self.devices)
        ])
        # The kubelet treats the end of the stream as a failure of the plugin
        while context.is_active() and not self.stop.wait(1):
            pass

    def GetPreferredAllocation(self, request, context):
        return api.PreferredAllocationResponse()

    def Allocate(self, request, context):
        return api.AllocateResponse(container_responses=[
            api.ContainerAllocateResponse(
                devices=[api.DeviceSpec(container_path=self.path, host_path=self.path, permissions="rw")],
                envs={"JOLT_JOBSERVER_PATH": self.path},
            )
            for _ in request.container_requests
        ])

    def PreStartContainer(self, request, context):
        return api.PreStartContainerResponse()

    def start(self) -> grpc.Server:
        """ Listen on the socket of the plugin, replacing a socket left behind. """
        try:
            os.unlink(self.socket)
        except FileNotFoundError:
            pass
        server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
        api_grpc.add_DevicePluginServicer_to_server(self, server)
        server.add_insecure_port("unix://" + self.socket)
        server.start()
        self.server = server
        return server

    def shutdown(self) -> None:
        self.stop.set()
        server, self.server = self.server, None
        if server is not None:
            server.stop(grace=None)
        try:
            os.unlink(self.socket)
        except FileNotFoundError:
            pass

    def register(self) -> None:
        kubelet = "unix://" + os.path.join(self.plugin_path, KUBELET_SOCKET)
        with grpc.insecure_channel(kubelet) as channel:
            api_grpc.RegistrationStub(channel).Register(
                api.RegisterRequest(
                    version=API_VERSION,
                    endpoint=self.endpoint,
                    resource_name=self.resource,
                    options=api.DevicePluginOptions(),
                ),
                timeout=10,
            )

    def serve(self) -> None:
        """ Serve the devices until shut down, registering again when the kubelet restarts. """
        while not self.stop.is_set():
            server = self.start()
            try:
                self.register()
            except grpc.RpcError as exc:
                log("[KUBERNETES] cannot register %s with the kubelet: %s\n", self.resource, exc.details())
                server.stop(grace=None)
                self.stop.wait(self.retry_interval)
                continue
            log("[KUBERNETES] registered %d %s devices with the kubelet\n", self.devices, self.resource)

            while os.path.exists(self.socket) and not self.stop.wait(self.retry_interval):
                pass
            if not self.stop.is_set():
                log("[KUBERNETES] the kubelet removed the plugin socket, registering again\n")
            server.stop(grace=None)
