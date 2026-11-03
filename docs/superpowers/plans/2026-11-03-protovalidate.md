# Protovalidate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Annotate the Jolt protobufs with protovalidate rules and enforce them in the scheduler and cache gRPC servers; separately raise Jolt's minimum Python to 3.11.

**Architecture:** A vendored `buf/validate/validate.proto` is imported by the protos. Go code imports the real `buf.validate` Go package. Python code imports a copy generated into `jolt/_vendor/buf/validate/`, reached by rewriting the generated import line. A new Go package `services/pkg/validate` provides unary and stream server interceptors, chained after authentication in both servers.

**Tech Stack:** protobuf, gRPC (Go and Python), `buf.build/go/protovalidate` v1.4.0, protovalidate `validate.proto` v1.2.2.

**Spec:** `docs/superpowers/specs/2026-11-03-protovalidate-design.md`

## Global Constraints

- Old and new versions of Jolt, the scheduler, the workers and the cache must keep working together; no rule may reject a message that any released sender produces.
- No `enum.defined_only`; no fixed lengths or hash algorithms on identities and digests.
- `jolt/plugins/deviceplugin.proto` is not changed.
- Clients don't validate; Jolt gets no protovalidate dependency.
- Invalid messages get `codes.InvalidArgument`; on streams this ends the stream.
- Authentication runs before validation.
- Minimum Python: 3.11.
- Commits, in order: Python 3.11 bump; annotations + vendored proto + Go dependency + regenerated code; interceptors.

## Rules

Decided from the senders: Python `jolt/plugins/scheduler.py` and `jolt/scheduler.py` (unchanged since `07dcd077`), Go `services/pkg/worker`, `services/cmd/schedulerctl`, and the external `fstree` for the cache. These are the only rules. Every other field stays unannotated:

| Field | Rule | Why it's safe |
|---|---|---|
| `Task.name` | `string.min_len = 1` | always `short_qualified_name` / task name |
| `Task.identity` | `string.pattern = "^[0-9a-f]+$"` | Python `hexdigest()`, Go `utils.Sha1String` |
| `BuildEnvironment.tasks` | `map.keys.string.min_len = 1` | keyed by exported task name |
| `BuildRequest.environment` | `required = true` | Python and schedulerctl always set it |
| `CancelBuildRequest.build_id` | `string.min_len = 1` | |
| `TaskRequest.build_id` | `string.min_len = 1` | set also in executor enlist messages |
| `TaskRequest.task_id` | `string.pattern = "^[0-9a-f]*$"` | empty in executor enlist messages |
| `TaskUpdate.request` | `required = true` | every sender sets it; `GetTasks` dereferences it and panics if nil |
| `ReadLogRequest.id` (both `log.proto` copies) | `string.min_len = 1` | |
| `ReadObjectRequest.digest` | `string.min_len = 1` | |
| `HasObjectRequest.digest` | `repeated.items.string.min_len = 1` | |
| `HasTreeRequest.digest` | `repeated.items.string.min_len = 1` | |

Deliberately not annotated: `Property.key` (a misconfigured worker property can yield an empty key that works today), `WriteObjectRequest.digest` (empty after the first chunk), `TaskUpdate.worker` (only in the enlist message), `BuildEnvironment.client` (schedulerctl leaves it unset), all enums, and messages that only servers send.

## Review Focus

- Executor enlist `TaskUpdate{request: {build_id: X}, worker: {id: W}}` with empty `task_id` and no status: must pass (Task 2 compatibility test).
- `BuildRequest` from `schedulerctl mock build`: empty `Workspace`, no `Client`, tasks keyed by name: must pass (Task 2).
- A `TaskStatus`/`LogLevel` value that doesn't exist yet (e.g. 99): must pass (Task 2 forward-compat test).
- A stream whose first message is valid and a later one is invalid: the stream ends with `InvalidArgument` at that message (Task 3).
- An unauthenticated call with an invalid message: gets `Unauthenticated`, not `InvalidArgument` (Task 3).

---

### Task 1: Raise the minimum Python version to 3.11

**Files:**
- Modify: `setup.py` (`python_requires`, drop `importlib_metadata` from `install_requires`)
- Modify: `jolt/plugins/selfdeploy.py:1,109-110` (use stdlib `importlib.metadata`)
- Modify: `README.rst:183` ("Python 3.11 or later"), `docs/installing.rst:11` ("Python 3.11+")

- [ ] **Step 1:** In `setup.py`, set `python_requires=">=3.11"` and remove `"importlib_metadata"` from the fallback `install_requires`. Keep `"zstandard; python_version < '3.14'"` and the `version_info < (3, 13)` check in `jolt/tasks.py`; both are still needed on 3.11.
- [ ] **Step 2:** In `jolt/plugins/selfdeploy.py`, replace `import importlib_metadata` with `from importlib import metadata as importlib_metadata`. The rest of the file can stay as is, because `distribution` and `PackageNotFoundError` have the same names in the stdlib.
- [ ] **Step 3:** Update the version in `README.rst` and `docs/installing.rst`.
- [ ] **Step 4:** Verify:
  Run: `python3 -c "import jolt.plugins.selfdeploy as s; print(s.get_extra_dependencies())"` → prints a list, no ImportError.
  Run: `cd tests && python3 -m jolt build -f flake8` → passes.
  Run: `python3 -m sphinx -b html docs <scratch>/docs` → no warnings.
- [ ] **Step 5: Commit**

```bash
git add setup.py jolt/plugins/selfdeploy.py README.rst docs/installing.rst
git commit -m "setup: require python 3.11"
```

### Task 2: Annotate the protos and regenerate the code

**Files:**
- Create: `third_party/protovalidate/buf/validate/validate.proto` (from `https://raw.githubusercontent.com/bufbuild/protovalidate/v1.2.2/proto/protovalidate/buf/validate/validate.proto`, unmodified)
- Modify: the 7 protos listed in the spec (annotations from **Rules**, plus `import "buf/validate/validate.proto";`)
- Modify: `build.jolt` `GenerateProtobufs` (include path, generate `validate_pb2.py`, relocate it, rewrite imports)
- Create: `jolt/_vendor/__init__.py`, `jolt/_vendor/buf/__init__.py`, `jolt/_vendor/buf/validate/__init__.py` (empty), and the generated `jolt/_vendor/buf/validate/validate_pb2.py`
- Modify: the regenerated `jolt/**/*_pb2.py` and `services/pkg/{protocol,cache}/*.pb.go`
- Modify: `services/pkg/protocol/pb.go`, `services/pkg/cache/cache_grpc.go` (`go:generate` lines get `-I../../../third_party/protovalidate`, cache gets `-I../../../third_party/protovalidate` relative to its own dir)
- Modify: `services/go.mod`, `services/go.sum`, `services/vendor/`
- Test: `services/pkg/protocol/validate_test.go`, `services/pkg/cache/validate_test.go`

**Interfaces:**
- Produces: annotated generated Go types in `pkg/protocol` and `pkg/cache`; `protovalidate.Validate(msg)` returns nil for the messages below.

- [ ] **Step 1: Add the Go dependency.** In `services/`: `go get buf.build/go/protovalidate@v1.4.0 && go mod tidy && go mod vendor`.
- [ ] **Step 2: Write the failing rule tests** in `services/pkg/protocol/validate_test.go` (package `protocol_test`, testify like the other tests). Use `protovalidate.Validate`:
  - `TestValidateAcceptsPythonBuildRequest`: environment with client, workspace, a property `config.x=y`, tasks `{"a/b:x=1": {name: "a/b:x=1", identity: <40 hex>, instance: <uuid>, platform: {node.os=linux}}}` → `NoError`.
  - `TestValidateAcceptsMockBuildRequest`: `Environment{Workspace: &Workspace{}, Tasks: {"t": {Name: "t", Identity: sha1("t")}}}`, no client → `NoError`.
  - `TestValidateAcceptsExecutorEnlist`: `TaskUpdate{Request: {BuildId: "b"}, Worker: {Id: "w"}}` → `NoError`.
  - `TestValidateAcceptsUnknownEnums`: `TaskUpdate{Request: {BuildId: "b", TaskId: "ab"}, Status: TaskStatus(99), Loglines: [{Level: LogLevel(99)}]}` → `NoError`.
  - `TestValidateAcceptsWorkerUpdate`: `WorkerUpdate{Status: ENLISTING, Platform: {Properties: [{Key: "", Value: "x"}]}}` → `NoError`.
  - `TestValidateRejects` (table, each `Error`): empty `Task.Name`; `Task.Identity` `"ABC"` and `""`; empty tasks map key; `BuildRequest{}` (nil environment); `CancelBuildRequest{}`; `TaskRequest{TaskId: "ab"}` (empty build id); `TaskRequest{BuildId: "b", TaskId: "xyz"}`; `TaskUpdate{}` (nil request); `ReadLogRequest{}`.
  - In `services/pkg/cache/validate_test.go`: `ReadObjectRequest{Digest: "sha1:<40 hex>"}`, `HasObjectRequest{Digest: ["<40 hex>"]}`, `HasTreeRequest{}` and `WriteObjectRequest{Data: []byte("x")}` → `NoError`; `ReadObjectRequest{}`, `HasObjectRequest{Digest: [""]}`, `HasTreeRequest{Digest: [""]}` → `Error`.
- [ ] **Step 3: Run them to see the rejection cases fail**
  Run: `cd services && go test ./pkg/protocol/ ./pkg/cache/ -run Validate`
  Expected: `TestValidateRejects` and the cache rejection cases FAIL (no rules yet); acceptance cases pass.
- [ ] **Step 4: Vendor `validate.proto` and annotate** the protos with exactly the rules in **Rules**, e.g. `string identity = 2 [(buf.validate.field).string.pattern = "^[0-9a-f]+$"];`. Note that `jolt/plugins/remote_execution/log.proto` and `services/pkg/logstash/log.proto` are copies; annotate both identically.
- [ ] **Step 5: Regenerate Go.** In `services/pkg/protocol` and `services/pkg/cache`: `nix-shell ../../../shell.nix --run "go generate"`. Generated imports must point at `buf.build/gen/go/bufbuild/protovalidate/protocolbuffers/go/buf/validate`. Make sure no `validate.pb.go` is generated into the repo.
- [ ] **Step 6: Run the Go tests**
  Run: `cd services && go build ./... && go test ./pkg/...`
  Expected: PASS, including all of Step 2.
- [ ] **Step 7: Python generation.** In `GenerateProtobufs`: `incpaths = [".", "third_party/protovalidate"]`; add `"third_party/protovalidate/buf/validate/validate.proto"` to `sources` with the `python` generator only (no gRPC stubs for it; if `protogenerator` can't be set per source, generate it in `run` with an extra `tools.run` of protoc inside the nix shell). In `publish`, collect the generated `buf/validate/validate_pb2.py` as `jolt/_vendor/buf/validate/validate_pb2.py` and, in every collected `*_pb2.py`, replace `from buf.validate import validate_pb2` with `from jolt._vendor.buf.validate import validate_pb2`. Do the rewrite in `run`, on the files in the output directory, so the artifact holds the final files.
- [ ] **Step 8: Regenerate Python**
  Run: `python3 -m jolt build -f jolt/protobufs -c <scratch>/gen` and copy `<scratch>/gen/jolt/**` over `jolt/`. Then create the three empty `__init__.py` files.
  Check: `git diff --stat jolt/` touches only the six non-deviceplugin `*_pb2.py` files plus the new `_vendor` files. `deviceplugin_pb2*.py` may only change if the generator version changed; otherwise revert it.
- [ ] **Step 9: Verify Python imports**
  Run: `python3 -I -c "import jolt.common_pb2, jolt.plugins.remote_execution.administration_pb2, jolt.plugins.remote_execution.log_pb2, jolt.plugins.remote_execution.scheduler_pb2, jolt.plugins.remote_execution.worker_pb2; import jolt.plugins.scheduler"` from the repo root → no error.
  Run: `grep -rn "^from buf" jolt/` → no output.
  Run: `cd tests && python3 -m jolt build -f flake8` → passes.
  Run: `python3 -m jolt build -f "int/scheduler"` if such a test exists (`ls tests/int_*sched*`), otherwise any API test touching remote execution → passes.
- [ ] **Step 10: Commit**

```bash
git add third_party build.jolt jolt services
git commit -m "protocol: add protovalidate annotations"
```

### Task 3: Validate incoming messages in the scheduler and cache

**Files:**
- Create: `services/pkg/validate/validate.go`, `services/pkg/validate/validate_test.go`
- Modify: `services/cmd/scheduler/grpc.go:53-54`, `services/cmd/cache/grpc.go:56-57`

**Interfaces:**
- Consumes: annotated types from Task 2.
- Produces: `func ServerOptions() []grpc.ServerOption` in package `validate`, returning `grpc.ChainUnaryInterceptor(unary)` and `grpc.ChainStreamInterceptor(stream)`. The unary interceptor validates `req`. The stream interceptor wraps `grpc.ServerStream` with a type whose `RecvMsg(m any) error` calls the embedded `RecvMsg`, then validates `m` if it is a `proto.Message`. Errors come from `func statusError(err error) error`: a `*protovalidate.ValidationError` becomes `status.New(codes.InvalidArgument, "invalid message: "+err.Error())` with `ve.ToProto()` attached through `WithDetails`. Any other validator error (a compilation failure) becomes `codes.Internal`.

- [ ] **Step 1: Write the failing tests** in `services/pkg/validate/validate_test.go`, using an in-process server over `bufconn` that registers `protocol.SchedulerServer`/`WorkerServer` fakes (embed the `Unimplemented*` types):
  - `TestUnaryRejectsInvalid`: `CancelBuild(&CancelBuildRequest{})` → `status.Code(err) == codes.InvalidArgument`, the fake handler not called, and `status.Convert(err).Details()` holds one `*validate.Violations`.
  - `TestUnaryPassesValid`: `CancelBuild({BuildId: "b"})` → handler called, no error.
  - `TestStreamRejectsLaterMessage`: `GetTasks` where the fake receives in a loop. The client sends a valid enlist `TaskUpdate{Request: {BuildId: "b"}}` and then `TaskUpdate{}`. The fake's first `Recv` succeeds, the second returns `InvalidArgument`, and the client's `Recv` gets `InvalidArgument`.
  - `TestServerStreamRequestValidated`: `ScheduleTask(&TaskRequest{TaskId: "zz"})` → `InvalidArgument` on the client's first `Recv`.
  - `TestAuthenticationFirst`: server options are `auth.ServerOptions` from an `Authenticator` that rejects (see `services/pkg/auth/auth_test.go` for constructing one), followed by `validate.ServerOptions()`. `CancelBuild(&CancelBuildRequest{})` without a token → `codes.Unauthenticated`.
- [ ] **Step 2: Run them**
  Run: `cd services && go test ./pkg/validate/`
  Expected: FAIL (package doesn't compile: `ServerOptions` undefined).
- [ ] **Step 3: Implement `ServerOptions`** in `services/pkg/validate/validate.go`, with one package-level validator from `protovalidate.New()`, created once. Panic on error at init, since it fails only on a programming error.
- [ ] **Step 4: Run the tests**
  Run: `cd services && go test ./pkg/validate/`
  Expected: PASS.
- [ ] **Step 5: Wire it in.** In both `grpc.go` files, append `validate.ServerOptions()...` after the `authenticator.ServerOptions(...)` line. gRPC runs chained interceptors in the order they were added, so authentication still comes first.
- [ ] **Step 6: Verify**
  Run: `cd services && go vet ./... && go test ./pkg/... && go build ./cmd/scheduler ./cmd/cache` → all pass.
  Run a local end-to-end check: start `go run ./cmd/scheduler` with its default config, then `go run ./cmd/schedulerctl mock build --task a` and `go run ./cmd/schedulerctl build stop ""`. The mock build schedules without errors, and the stop with an empty id reports `InvalidArgument`. If the scheduler can't run locally without extra setup, skip this step and say so in the report.
- [ ] **Step 7: Commit**

```bash
git add services/pkg/validate services/cmd/scheduler/grpc.go services/cmd/cache/grpc.go
git commit -m "services: validate incoming grpc messages"
```
