package scheduler

import (
	"context"
	"net"
	"testing"
	"time"

	"github.com/srand/jolt/scheduler/pkg/protocol"
	"github.com/srand/jolt/scheduler/pkg/utils"
	"github.com/stretchr/testify/require"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
)

func TestClientReconnect(t *testing.T) {
	for _, scenario := range []struct {
		name           string
		evict          bool
		unacknowledged bool
	}{
		{name: "evicted", evict: true},
		{name: "retained_after_acknowledgment"},
		{name: "retained_before_acknowledgment", unacknowledged: true},
	} {
		t.Run(scenario.name, func(t *testing.T) {
			s := NewPriorityScheduler()
			listener, err := net.Listen("tcp", "127.0.0.1:0")
			require.NoError(t, err)
			server := grpc.NewServer()
			protocol.RegisterSchedulerServer(server, NewSchedulerService(s))
			go server.Serve(listener)
			t.Cleanup(server.Stop)

			ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
			defer cancel()
			request := buildEventRequest()
			const taskID = "target"
			connect := func() (protocol.SchedulerClient, string, *grpc.ClientConn) {
				conn, err := grpc.NewClient(listener.Addr().String(), grpc.WithTransportCredentials(insecure.NewCredentials()))
				require.NoError(t, err)
				t.Cleanup(func() { conn.Close() })
				client := protocol.NewSchedulerClient(conn)
				stream, err := client.ScheduleBuild(ctx, request)
				require.NoError(t, err)
				update, err := stream.Recv()
				require.NoError(t, err)
				require.Equal(t, protocol.BuildStatus_BUILD_ACCEPTED, update.GetStatus())
				return client, update.GetBuildId(), conn
			}
			submit := func(client protocol.SchedulerClient, build *priorityBuild) grpc.ServerStreamingClient[protocol.TaskUpdate] {
				stream, err := client.ScheduleTask(ctx, &protocol.TaskRequest{BuildId: build.Id(), TaskId: taskID})
				require.NoError(t, err)
				require.Eventually(t, func() bool {
					// Wait for ScheduleTask to release its lock after updating the queue.
					s.RLock()
					defer s.RUnlock()
					return build.tasks[taskID].HasObserver()
				}, 2*time.Second, time.Millisecond, "scheduler did not attach the task stream")
				return stream
			}
			newWorker := func() Worker {
				worker, err := s.NewWorker(NewPlatform(), NewPlatform())
				require.NoError(t, err)
				t.Cleanup(worker.Close)
				return worker
			}
			dispatch := func(build *priorityBuild, worker Worker) Executor {
				// Drive a single scheduling pass with a known idle, compatible worker.
				s.requeueReadyBuilds()
				s.selectTaskAndWorker()
				select {
				case assigned := <-worker.Builds():
					require.Same(t, build, assigned)
				case <-ctx.Done():
					t.Fatal(ctx.Err())
				default:
					t.Fatalf("no dispatch: status=%s queued=%t assigned=%t", build.tasks[taskID].Status(),
						build.HasQueuedTask(), build.tasks[taskID].IsAssigned())
				}
				executor, err := s.NewExecutor(worker.Id(), build.Id())
				require.NoError(t, err)
				t.Cleanup(executor.Close)
				select {
				case task := <-executor.Tasks():
					require.Same(t, build.tasks[taskID], task)
				case <-ctx.Done():
					t.Fatal(ctx.Err())
				}
				return executor
			}

			client, id, conn := connect()
			registered, err := s.GetBuild(id)
			require.NoError(t, err)
			original := registered.(*priorityBuild)
			t.Cleanup(original.Close)
			task := original.tasks[taskID]
			submit(client, original)
			executor := dispatch(original, newWorker())

			// Drop the connection, not the build. The worker finishes without the client.
			require.NoError(t, conn.Close())
			require.Eventually(t, func() bool {
				return !original.HasObserver() && !task.HasObserver()
			}, 2*time.Second, time.Millisecond)
			task.PostStatusUpdate(protocol.TaskStatus_TASK_PASSED)
			if !scenario.unacknowledged {
				executor.Acknowledge()
				executor.Close()
			}
			if scenario.evict {
				s.removeStaleBuilds()
				_, err := s.GetBuild(id)
				require.ErrorIs(t, err, utils.ErrNotFound)
			}

			client, reconnectedID, _ := connect()
			require.Equal(t, id, reconnectedID)
			registered, err = s.GetBuild(id)
			require.NoError(t, err)
			current := registered.(*priorityBuild)
			if scenario.evict {
				t.Cleanup(current.Close)
				require.NotSame(t, original, current)
				require.Equal(t, protocol.TaskStatus_TASK_CREATED, current.tasks[taskID].Status())
			} else {
				require.Same(t, original, current)
				require.Equal(t, protocol.TaskStatus_TASK_PASSED, task.Status())
			}

			stream := submit(client, current)
			if scenario.unacknowledged {
				// Hold the acknowledgment until after the retry finishes ScheduleTask.
				executor.Acknowledge()
				executor.Close()
			}
			require.True(t, current.HasQueuedTask(), "retry was lost before dispatch (status=%s)", current.tasks[taskID].Status())
			dispatch(current, newWorker())
			for {
				update, err := stream.Recv()
				require.NoError(t, err)
				if update.GetStatus() != protocol.TaskStatus_TASK_QUEUED {
					require.Equal(t, protocol.TaskStatus_TASK_ASSIGNED, update.GetStatus())
					break
				}
			}
		})
	}
}
