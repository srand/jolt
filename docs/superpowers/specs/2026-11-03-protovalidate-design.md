# Protovalidate annotations for the Jolt protobufs

## Intent

Make the remote execution protocol more robust by declaring, with
[protovalidate](https://protovalidate.com) annotations, what a well-formed message
looks like, and by checking every message that the Go servers receive. There is
no specific incident behind this: the goal is that a malformed message is
rejected at the boundary with a clear error, instead of travelling into the
scheduler or the cache and failing somewhere obscure.

## Goals

- Annotate the fields of these protos with `buf.validate` rules:
  - `jolt/common.proto`
  - `jolt/plugins/remote_execution/administration.proto`
  - `jolt/plugins/remote_execution/log.proto`
  - `jolt/plugins/remote_execution/scheduler.proto`
  - `jolt/plugins/remote_execution/worker.proto`
  - `services/pkg/cache/cache.proto`
  - `services/pkg/logstash/log.proto`
- The scheduler and the cache check every unary request and every incoming
  stream message.
- Separately, raise Jolt's minimum Python version to 3.11, the oldest version
  that still has official support (3.10 reached end of life in October 2026).

## Non-goals

- `jolt/plugins/deviceplugin.proto` is a copy of the Kubernetes device plugin API
  and is left untouched.
- Clients don't check what they receive: not Jolt (client and executor), not the
  worker, not `schedulerctl`. Jolt gets no protovalidate dependency.
- Messages are not checked before they are sent, and servers don't check their
  responses.
- No new limits that the code doesn't already rely on (maximum sizes, rate limits
  and so on). The annotations describe the protocol as it is.

## Anti-goals

These would make the work a failure even if every message validates:

- **Breaking mixed versions.** Old and new versions of Jolt, the scheduler, the
  workers and the cache must keep working together. During an upgrade, an older
  client talks to a newer scheduler.
- **Rejecting a message that works today.**

## Constraints

### Rules must hold in both directions

A rule is a contract between every released sender and every released receiver:

- A new server checks messages from old clients. A rule must accept everything
  that any released version of the sender produces. Before a field gets a rule,
  check every place that builds the message (Python in `jolt/`, Go in
  `services/`, including the worker and `schedulerctl`) and its history in git
  for versions that left the field empty or formatted it differently.
- An old server will check messages from future clients with the rules as they
  are now. A rule that a future version might reasonably want to break locks the
  protocol. In particular:
  - No `enum.defined_only` on enums that can grow (`TaskStatus`, `BuildStatus`,
    `LogLevel`, `WorkerRequest.Action`, `WorkerUpdate.Status`).
  - No fixed lengths or algorithms for digests and identities. `Digest` and
    `Workspace.tree` already carry an algorithm, cache digests are `alg:hex`
    (`utils.ParseDigest`), and the identity hash may change one day.
  - No `required` on a field whose meaning might later be replaced by a new field.

When in doubt, leave the field without a rule. A missing rule costs nothing; a
wrong rule breaks a deployment.

Since annotations live on messages, they also apply to messages that servers
only send (`BuildUpdate`, `ListBuildsResponse`, `SchedulerEvent`). Those are never
checked, so annotating them is documentation only; keep it to what is certain.

### Rules that are expected to be safe

As a guide for the builder, and subject to the checks above:

- Identifiers that the server indexes on are non-empty: `Task.identity`,
  `CancelBuildRequest.build_id`, `ReadLogRequest.id`, cache `digest`s. Note
  that `CANCEL_BUILD` instructions carry an empty `BuildRequest`.
- Not `TaskRequest`: the executor's first message has no `task_id`, and the
  client can send an empty `build_id` after a race with a failed request, which
  the scheduler answers with `NotFound` and the client retries.
- No format for identities: a hex pattern would reject a future `alg:hex` form.
- Required sub-messages that the server dereferences, for example
  `BuildRequest.environment` and `BuildEnvironment.client`/`workspace`, if every
  released client sets them.
- `map<string, Task> BuildEnvironment.tasks`: the key equals `Task.identity`, if
  that has always held.
- `Property.key` is non-empty.

### Generated code and dependencies

- Vendor `buf/validate/validate.proto` from protovalidate v1.2.2, the latest
  tagged release. `buf.build/go/protovalidate` v1.4.0 pins an untagged Buf
  registry commit from August 2026, which may have more rules, but the vendored
  copy only has to declare the rules these protos use. Add it to the include path of
  both generators: `GenerateProtobufs` in `build.jolt` (Python) and the
  `go:generate` lines in `services/pkg/protocol/pb.go` and
  `services/pkg/cache/cache_grpc.go`.
- **Go:** the generated code imports the `buf.validate` package that
  `buf.build/go/protovalidate` depends on. The services vendor their
  dependencies: run `go mod vendor` after adding it.
- **Python** (decided by Claude): no PyPI package ships `buf.validate.validate_pb2`,
  protovalidate included. `GenerateProtobufs` also generates `validate_pb2.py`
  into Jolt's own package (for example `jolt/_vendor/buf/validate/`) and rewrites
  the `from buf.validate import validate_pb2` line of the generated files to
  import it from there. This avoids shipping a top-level `buf` package that could
  clash with other installs, and needs no changes to worker deployment or
  selfdeploy, which collect `jolt/**`. The only runtime dependency is `protobuf`;
  check that the generated module loads with the oldest `protobuf` Jolt allows.

### Python 3.11 (separate commit)

- `python_requires=">=3.11"` and the classifiers in `setup.py`; remove code paths
  and markers that only exist for 3.9 and 3.10 (`python_version` markers,
  `importlib_metadata` fallbacks, `sys.version_info` checks).
- CI already runs 3.12 and 3.14t; the Docker images use Python 3.14 and Debian
  stable, which are fine.

## How messages are checked

A shared package (for example `services/pkg/validate`) provides a unary and a
stream server interceptor. The stream interceptor wraps the `grpc.ServerStream`
so that every `RecvMsg` is checked.

- They are chained after the authentication interceptors in
  `services/cmd/scheduler/grpc.go` and `services/cmd/cache/grpc.go`, so that
  unauthenticated calls keep failing with `Unauthenticated` before anything is
  checked.
- A message that fails gets `codes.InvalidArgument`, with a readable message
  (field path and rule) and the violations as error details.
- On streams, an invalid message ends the stream with `InvalidArgument` (decided
  by Claude). On `GetInstructions` and `GetTasks` the worker or executor then
  treats the scheduler as lost. Under the compatibility rule above, no released
  sender produces invalid messages, so this only happens because of a bug, and
  failing loudly makes it visible.

## Testing

- **Compatibility, the most important test:** messages built the way the current
  Jolt client, worker and `schedulerctl` build them (a `BuildRequest` from a real
  test build, task updates, worker updates, cache requests) pass validation.
  Where older releases built a message differently, add that shape too.
- **Forward compatibility:** a message with an enum value that doesn't exist yet,
  and with unknown fields, passes.
- Each rule has a case that it rejects.
- The interceptors return `InvalidArgument` for invalid unary requests and
  stream messages, and leave valid ones alone; authentication still happens
  first.
- `go test ./pkg/...`, `python3 -m jolt build flake8` and the existing remote
  execution tests pass; Jolt still imports its regenerated `_pb2` modules.

## Delivery

Separate commits, in this order:

1. Raise the minimum Python version to 3.11.
2. Add the annotations, the vendored `validate.proto`, the Go dependency and the
   regenerated Python and Go code.
3. Check messages in the scheduler and the cache.

## Left to the builder

- The exact rule on each field, within the constraints above.
- Where the vendored `validate.proto` lives.
- The wording of error messages and the layout of the shared Go package.
