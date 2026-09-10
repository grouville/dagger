# Ordinary Rust check loop

This is a small platform-overhead fixture, not the official Rust module and not
a real-project, fully cold, or Bazel comparison. No session retention, custom
mutable snapshot APIs, or resident CLI is used. The Dagger engine persists,
as do Cargo target caches. Image provisioning and target warmup are excluded.

Build the engine/CLI with `./hack/dev`, then run:

```sh
./hack/with-dev python3 hack/bench-rust-loop/run.py \
  --dagger ./bin/dagger \
  --image rust@sha256:0e2bcaef56d041a486784e54104a81aebe0da44bd03019bd70bc0401e42e4a97
```

Requires Docker, Git and Python 3.11+. Output is preserved in a printed temporary
directory: raw command logs, paired timings, metadata, and a wcprof diagnostic
capture. Each run creates a unique fixture and target-cache namespace. Only its
named native container is removed automatically; files and engine cache remain.
Use ordinary engine cache GC for the latter. Run without competing builds.

Both sides run `cargo check --workspace --locked` with the same image, source and
target paths. The native timer includes `docker exec` (not a raw host Cargo
baseline). Application/library edits are unique within a run. A deliberate
compile error followed by repair checks that Dagger consumes changed input.
All samples, including outliers, are retained. No-change and edited workloads
are reported separately. A profiled repair is outside the headline timing set.

Analyze `library-repair.wcprof` with the separately maintained wcprof analyzer.
The in-tree README's `go run ./cmd/wcprof-analyze` command is stale: the analyzer
was removed in e3b4e9c820. The last public analyzer can be extracted from that
commit's parent for diagnostic use, but label that fallback and do not treat its
counterfactual estimates as measured savings.

Check event drops and unresolved waits before interpreting critical-path
rankings. Validate optimization hypotheses with paired unprofiled runs. Preserve
engine image/binary identity alongside results when changing deployments.

Remaining coverage: real repositories, external dependency-version changes,
Clippy/tests/fmt, artifact generation/export, cold installation, concurrent CLI
calls, remote engines and macOS. This fixture cannot establish those claims.

## Current-main validation (2026-09-10)

On engine/CLI built from 59a9b904d1 with `hack/dev`, the first run reached the
deliberate compile error and returned Cargo's exit code 101. A second complete
run returned **0** for that same invalid source. The harness correctly rejects
the second result; timings must not be interpreted as a verified performance
win. The source file read directly through the engine contained `compile_error!`.
A subsequent wcprof capture showed `Container.withExec` as a cache hit and no
process execution. A different, unique compile error failed twice with 101.
Cargo alone reproduced the underlying freshness hazard: after a successful
check, replace the library with a compile error but set its mtime to an older
date. Cargo returns 0; updating that mtime makes it return 101. Immutable source
reuse can preserve older timestamps while a mutable target contains newer
fingerprints. The diagnostic exec confirmed the invalid source's old mtime.

The source-sync candidate uses standard rsync checksum comparison into a locked
source cache before Cargo. It deliberately does not preserve source timestamps:
changed files receive fresh timestamps, unchanged files remain untouched, and
deleted paths are removed. The source and target caches use existing Dagger
LOCKED mounts; no engine API or lifecycle changes are required. The harness also
revisits the original failing source after a successful repair.

Rsync is installed in a cached toolchain layer for this experiment. This adds
provisioning work and is not a demonstrated one-second cold-install solution.
The first source-sync run passed failure/repair. Seven-sample medians (ms):

| Scenario | Cargo via docker exec | Dagger CLI |
| --- | ---: | ---: |
| Exact | 111.97 | 1101.42 |
| Application edit | 125.20 | 1258.44 |
| Workspace-library edit | 137.74 | 1239.25 |

Separate library-repair wcprof capture: 367.1 ms recorded span, 204.8 ms command
time, 354 ops, no open ops or dropped events. Exact capture: 140.4 ms. These are
diagnostic samples, not the medians above; engine spans do not cover the full
CLI lifecycle. CLI startup in this environment repeatedly attempted an expired
LLM OAuth refresh. Do not extrapolate these small-fixture results to ripgrep.

This branch is a diagnostic baseline, not an optimized or fully validated module.
The fixed error string is intentional: repeated fixture runs should not turn a
previously rejected source into a successful check.
