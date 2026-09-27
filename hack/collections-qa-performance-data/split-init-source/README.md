# Split-init prototype: prepared, not executed

Historical preparation note: the statements below describe the snapshot before
validation. See `result-report.md` for the subsequently completed normal/race,
privileged PID1, build and startup-micro results. The preserved source manifest
remains an input record from that earlier preparation point.

No shared source changes, builds, tests, engine calls, or timing runs have been
performed for this prototype. HEAD and original/candidate source hashes are in
`manifest.json`. All tests remain unvalidated drafts until the parent schedules
a heavy slot.

`source-overlay.json` contains five production source replacements/additions.
`test-overlay.json` adds the two focused test files. `prototype.patch` is the
production-only diff; `tests.patch` is separate. `prepare.py` creates the source
snapshot and runs gofmt only. It does not test or build.

The light command imports only the standard library, x/sys/unix, and the
constants-only distconsts package. Its mainInit body is copied byte-for-byte
from the original. The heavy helper retains all current provider code and
legacy dispatch aliases. Adding `/.dagger-session` selects the same mainSession.
PID1 starts it as a separate process and retains the existing FD3 readiness
protocol and timeout. Only the command construction is factored to support
protocol tests; there is no environment-controlled helper executable override.

Packaging retains the original `/usr/local/bin/dagger-init` and adds
`/usr/local/bin/dagger-init-lite`. Executor mounts light at `/.init` and heavy
at `/.dagger-session`, both read-only. A future measured engine must include
both artifacts; replacing the engine binary alone is insufficient. NoInit
retains its original arguments and skips both mounts. Both mounts are initially
present for ordinary and nested initialized execs: this preserves explicit
session-environment behavior but introduces another reserved container file and
bind mount. Measure that overhead as part of the prototype, not separately
subtracting it from an expected saving.

Prepared tests:

- `TestSplitInitReadiness`: the caller stays blocked before FD3 closes, then
  returns while the helper is still alive; helper death preserves the existing
  EOF protocol.
- `TestSplitInitHelperStartError`: missing helper remains a startup error.
- `TestSplitInitArgvAndExitStatus` and `TestSplitInitSignalForwarding`: real
  subprocesses retain argv and user exit status, and receive group-forwarded
  signals.
- `TestSplitInitPIDNamespaceReaping`: explicit privileged opt-in, real PID1
  namespace, orphan process exits and is reaped. No host /proc traversal or
  signaling of pre-existing processes.
- `TestSplitInitMounts`: ordinary/nested read-only source/destination/argv
  contract and both NoInit variants.

Proposed focused commands, not run:

```sh
GOMAXPROCS=4 GOTOOLCHAIN=local GOPROXY=off \
  /home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go \
  test -overlay=/tmp/collections-perf/split-init-prototype-v1/test-overlay.json \
  ./cmd/init-lite -run='^TestSplitInit' -count=1 -timeout=60s

GOMAXPROCS=4 GOTOOLCHAIN=local GOPROXY=off \
  /home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go \
  test -overlay=/tmp/collections-perf/split-init-prototype-v1/test-overlay.json \
  ./engine/engineutil -run='^TestSplitInitMounts$' -count=1 -timeout=60s
```

Repeat focused tests with `-race` after normal gates pass. The PID1 case requires
`DAGGER_TEST_INIT_PID_NAMESPACE=1` only in a task-owned privileged test container;
its absence is a reported skip, not proof of reaping correctness. The actual
Go/Python/TypeScript nested attachable/provider and ordinary exec smoke matrix,
TTY behavior, cleanup, build/platform packaging and full CLI timing remain
separate mandatory integration gates. No raw profiles or helper logs belong in
the shareable evidence directory.

The original init contains pipe-descriptor and helper-failure protocol details
that this draft intentionally preserves; do not silently fix them while timing
the process split. This is an architectural experiment, not an upstream-ready
change or a claim that the entire 58/67 ms prefix is package initialization.
