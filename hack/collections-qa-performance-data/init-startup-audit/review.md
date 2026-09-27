# PID1 and nested admission: source audit

Status: source review only; no new build, runtime, or performance result.

The existing Linux init executable has two modes. Both initialize the same Go
imports before `main` selects a mode: PID1 (`/.init`) and attachables
(`/proc/self/exe`). For a nested exec, PID1 starts a second instance of itself and
waits for FD3 to close before starting the user's command. The imports include
engine/client, Git, filesync, secret and socket providers. A separate lightweight
PID1 executable can avoid initializing that graph in the parent while leaving
the attachables process and its authority unchanged. A runtime branch or another
file in the existing package would not remove package initialization.

Keep the helper process. PID1's `Wait4(-1, WNOHANG)` reaps children and adopted
orphans. Moving providers into PID1 goroutines would make their Git/secret
`exec.Cmd` children compete with that reaper; `Cmd.Wait` could lose its child.
The helper also has its own session/process group. Preserve that separation,
the FD3 protocol, stdio, environment, signal forwarding, TTY handling, and
shutdown behavior. Existing EOF means either ready or helper death: changing
this error protocol belongs in a separate change.

Smallest concrete prototype: retain `cmd/init` as the heavy helper, add a
lightweight `cmd/init-lite`, package both, and explicitly bind the helper at a
reserved read-only path in each initialized execution. The heavy executable
needs only an additional dispatch alias; provider code stays unchanged. The
prototype initially keeps both mounts for all initialized execs to preserve
behavior even when session environment variables are supplied explicitly.
`NoInit` skips both mounts and argument injection. The extra bind mount and
extra reserved file are costs/observable changes to review, not free work.

The saved constructor and method profiles have 58.173 ms and 66.649 ms between
the runc-monitor started callback and first recorded nested `serveQuery`.
Those are not measurements of package initialization or authored method bodies.
The callback is emitted when go-runc has started its monitor process. The gap
can contain runc/container startup, both init processes, attachable setup,
user/SDK initialization, and nested HTTP admission. The proposed split has no
measured saving yet.

Minimum next profiling change:

1. For an already opted-in nested session, enable native wcprof context before
   `getOrInitClient`, deriving the decision from trusted injected metadata or
   existing session/global profiling state. Do not introduce an authority or
   arbitrary-header shortcut.
2. Add fixed numeric phases for nested admission and `initializeClientRuntime`.
   End admission before dispatching the endpoint; do not measure a long-lived
   stream as startup.
3. Split attachables HTTP upgrade/ACK from registration-to-publication. Stop
   registration timing after the caller is installed and waiters are woken.
   `Register` then waits until disconnect, so timing its entire lifetime would
   be misleading. Retain the deliberate OTel/gRPC metrics suppression.
4. Compare first nested arrival, admission, readiness and first query. Only if
   the remaining pre-arrival gap warrants it, add separate diagnostic process
   entry/readiness timestamps or init tracing. Keep those captures outside
   ordinary timings, with numeric/static labels and no secrets, IDs, URLs,
   source or payloads in public evidence.

Future correctness gates: exact argv/env/stdio and exit status; signal forwarding
and TTY stop/continue; orphan reaping as real namespace PID1; FD3 readiness while
the helper remains alive; helper failure/start error; provider subprocesses
without ECHILD; nested Go/Python/TypeScript calls; ordinary exec and NoInit;
attachables/service cleanup. First measure the complete CLI including cleanup,
then attribute any change using separate profiling runs.

Source anchors: `cmd/init/main.go` main/mainInit/startSessionSubprocess/mainSession;
`engine/engineutil/executor_spec.go` injectInit/setupNestedClient/run process
started callback; `engine/engineutil/executor.go` procHandle.WaitForStart;
`.dagger/modules/engine-dev/build/builder.go` binary packaging/daggerInit;
`engine/distconsts/consts.go` artifact paths; `engine/server/session.go`
ServeHTTPToNestedClient/serveHTTPToClient/getOrInitClient/initializeClientRuntime/
serveSessionAttachables/serveQuery; `engine/server/session_attachables.go`
Register; `engine/session/git/git_credential.go` and
`engine/client/secretprovider/cmd.go` subprocess ownership.
