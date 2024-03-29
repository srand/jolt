# Generated by the gRPC Python protocol compiler plugin. DO NOT EDIT!
"""Client and server classes corresponding to protobuf-defined services."""
import grpc

from jolt.plugins.remote_execution import scheduler_pb2 as jolt_dot_plugins_dot_remote__execution_dot_scheduler__pb2


class SchedulerStub(object):
    """The scheduler service
    """

    def __init__(self, channel):
        """Constructor.

        Args:
            channel: A grpc.Channel.
        """
        self.ScheduleBuild = channel.unary_stream(
                '/Scheduler/ScheduleBuild',
                request_serializer=jolt_dot_plugins_dot_remote__execution_dot_scheduler__pb2.BuildRequest.SerializeToString,
                response_deserializer=jolt_dot_plugins_dot_remote__execution_dot_scheduler__pb2.BuildUpdate.FromString,
                )
        self.CancelBuild = channel.unary_unary(
                '/Scheduler/CancelBuild',
                request_serializer=jolt_dot_plugins_dot_remote__execution_dot_scheduler__pb2.CancelBuildRequest.SerializeToString,
                response_deserializer=jolt_dot_plugins_dot_remote__execution_dot_scheduler__pb2.CancelBuildResponse.FromString,
                )
        self.ScheduleTask = channel.unary_stream(
                '/Scheduler/ScheduleTask',
                request_serializer=jolt_dot_plugins_dot_remote__execution_dot_scheduler__pb2.TaskRequest.SerializeToString,
                response_deserializer=jolt_dot_plugins_dot_remote__execution_dot_scheduler__pb2.TaskUpdate.FromString,
                )


class SchedulerServicer(object):
    """The scheduler service
    """

    def ScheduleBuild(self, request, context):
        """Create a new build in the scheduler.
        The build is not started until tasks are scheduled.
        """
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def CancelBuild(self, request, context):
        """Cancel a build.
        """
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def ScheduleTask(self, request, context):
        """Schedule a task to be executed.
        The scheduler will assign the task to a free worker
        and updates will be sent back once the task is running.
        """
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')


def add_SchedulerServicer_to_server(servicer, server):
    rpc_method_handlers = {
            'ScheduleBuild': grpc.unary_stream_rpc_method_handler(
                    servicer.ScheduleBuild,
                    request_deserializer=jolt_dot_plugins_dot_remote__execution_dot_scheduler__pb2.BuildRequest.FromString,
                    response_serializer=jolt_dot_plugins_dot_remote__execution_dot_scheduler__pb2.BuildUpdate.SerializeToString,
            ),
            'CancelBuild': grpc.unary_unary_rpc_method_handler(
                    servicer.CancelBuild,
                    request_deserializer=jolt_dot_plugins_dot_remote__execution_dot_scheduler__pb2.CancelBuildRequest.FromString,
                    response_serializer=jolt_dot_plugins_dot_remote__execution_dot_scheduler__pb2.CancelBuildResponse.SerializeToString,
            ),
            'ScheduleTask': grpc.unary_stream_rpc_method_handler(
                    servicer.ScheduleTask,
                    request_deserializer=jolt_dot_plugins_dot_remote__execution_dot_scheduler__pb2.TaskRequest.FromString,
                    response_serializer=jolt_dot_plugins_dot_remote__execution_dot_scheduler__pb2.TaskUpdate.SerializeToString,
            ),
    }
    generic_handler = grpc.method_handlers_generic_handler(
            'Scheduler', rpc_method_handlers)
    server.add_generic_rpc_handlers((generic_handler,))


 # This class is part of an EXPERIMENTAL API.
class Scheduler(object):
    """The scheduler service
    """

    @staticmethod
    def ScheduleBuild(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_stream(request, target, '/Scheduler/ScheduleBuild',
            jolt_dot_plugins_dot_remote__execution_dot_scheduler__pb2.BuildRequest.SerializeToString,
            jolt_dot_plugins_dot_remote__execution_dot_scheduler__pb2.BuildUpdate.FromString,
            options, channel_credentials,
            insecure, call_credentials, compression, wait_for_ready, timeout, metadata)

    @staticmethod
    def CancelBuild(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(request, target, '/Scheduler/CancelBuild',
            jolt_dot_plugins_dot_remote__execution_dot_scheduler__pb2.CancelBuildRequest.SerializeToString,
            jolt_dot_plugins_dot_remote__execution_dot_scheduler__pb2.CancelBuildResponse.FromString,
            options, channel_credentials,
            insecure, call_credentials, compression, wait_for_ready, timeout, metadata)

    @staticmethod
    def ScheduleTask(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_stream(request, target, '/Scheduler/ScheduleTask',
            jolt_dot_plugins_dot_remote__execution_dot_scheduler__pb2.TaskRequest.SerializeToString,
            jolt_dot_plugins_dot_remote__execution_dot_scheduler__pb2.TaskUpdate.FromString,
            options, channel_credentials,
            insecure, call_credentials, compression, wait_for_ready, timeout, metadata)
