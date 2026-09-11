# Ordinary Rust check loop

This is a platform-overhead fixture with an optional pinned ripgrep workload,
not the official Rust module, a fully cold comparison, or a Bazel comparison. No session retention, custom
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

For the real-project workload, add `--ripgrep /path/to/clean/ripgrep`. The script
requires revision `3fce3b5bb0236da2df6d99672afb8a719642eca7` and copies it into
isolated workspaces. Application edits change the version output string; library
edits change grep-printer's omitted-context output. Diagnostic `check-log` calls
outside the timers retrieve the evaluated Cargo action's stderr, permitting
comparison of the rebuilt package chains with the native logs.

The module now mounts registry/Git caches as well as target/source caches. A
first diagnostic real-project pass without these mounts was asymmetric with the
persistent native container and must not be used as the headline comparison.
Both sides prime downloads and targets before warm-loop timing; no cold claim.

Both sides run `cargo check --workspace --locked` with the same image, source and
target paths. The native timer includes `docker exec` (not a raw host Cargo
baseline). Application/library edits are unique within a run. A deliberate
compile error followed by repair checks that Dagger consumes changed input.
All samples, including outliers, are retained. No-change and edited workloads
are reported separately. A profiled repair is outside the headline timing set.

## Reset / first-use loop

Add `--fresh-engine localhost/dagger-engine.dev` to create a uniquely named
engine container, empty engine-state volume, and fresh XDG CLI state per trial.
The engine image must already exist locally. The script deletes only the engine
container/volume it creates, even if the check fails; source copies, logs and
results remain in the printed directory. Existing engine and Cargo caches are
not cleared. Docker's shared image store and OS page cache are not reset.

Repeat the command to repeat the reset. Each trial measures provisioning through
the first Dagger check before priming Dagger, records native's first check and
an existing-cache check, then retains caches for application/library edits.
`first-use.json` stores the phase timings. Add `--profile-first` for a separate
diagnostic trial that captures `first-check.wcprof`; do not mix that trial into
unprofiled headline timings. Engine readiness is included in the elapsed first
check, not overlapped with native compilation.

This is **engine-cache cold**, not a complete installation benchmark: Docker,
the CLI, the engine image, local module source, and native Rust image already
exist. Their download/install costs remain explicitly unmeasured. A complete
new-user journey must add those costs and a public module install step.

`--pinned-source-sync` opts into a packaging experiment for the pinned
slim-bookworm/amd64 image: verified Debian rsync/libpopt files replace runtime
APT resolution. Downloads and installation remain inside the first check.
This is not a cross-platform default; see [the delivery experiment](source-sync-delivery-results.md)
for the cold gain, measured warm regression, correctness checks and limitations.

`--project-toolchain fixtures/rust-toolchain-rustfmt.toml` copies the exact same
toolchain file into both isolated workspaces before their first checks. Component
installation is included in the first-check timer, not done in a hidden warmup.
Existing project toolchain files are never replaced. `--prepare-project-toolchain`
opts the Dagger side into a separate immutable setup action that reads only the
root `rust-toolchain` / `rust-toolchain.toml` files. Ordinary source edits should
reuse that setup; changes to the toolchain configuration must invalidate it.
The native container naturally retains its installed components across commands.

The candidate uses explicit `rustup toolchain install --no-self-update`,
validated with the pinned image's rustup 1.29.0. It does not set
`RUSTUP_TOOLCHAIN`, change Cargo arguments, or create a mutable rustup cache.
With no toolchain file it skips setup entirely (but still pays for the filtered
directory lookup). This is a root-workspace experiment, not the final official
module: nested Cargo working directories, custom toolchain paths, explicit
overrides, rolling-channel updates and cross-platform delivery need separate
compatibility validation. Its pinned fixture requests the already selected
compiler plus rustfmt; it does not substitute a faster compiler.

`python3 hack/bench-rust-loop/test-toolchain.py --dagger ./bin/dagger` runs a
separate correctness-only suite against the selected engine. It adds a component,
changes/repairs/removes configuration, tests legacy-file precedence and checks a
source failure/repair. It inspects the prepared toolchain's component manifest
directly, without a rustup proxy invocation that could mask a missing component.
All inputs, command outputs and process boundaries are retained in its printed
temporary directory. Only its own temporary toolchain files are removed during
the deletion tests; previous contents remain in per-check input records.

Both `run.py` and `test-toolchain.py` accept `--module-dir /path/to/variant`
for opt-in comparisons of local module implementations with the same CLI and
engine. The default remains this directory's `module/`. A variant must contain
`main.dang` and `dagger-module.toml` and implement the same fixture API/settings;
this option does not install a public module or establish workload equivalence.
Keep variants unchanged during a run. Each script records the resolved module
path, `module_sha256` (the main file), and `module_config_sha256` in
`metadata.json`. `source_root`, `source_commit`, and `source_diff_sha256` describe
the harness repository, even when the selected module is outside Git. Dependency
upgrade patches still come from the committed `fixtures/`, never the variant.
Run the correctness suite for each variant and compare identical workloads;
alternate variant order across separate runs and retain all samples.

`compare-module-edits.py` compares two module variants on alternating novel
application/library edits against the same engine and CLI. It deliberately
accepts only matching pinned ripgrep workspaces produced by `run.py`, verifies
the recorded module/CLI hashes and settings, and requires `--execute` plus an
explicit `DAGGER_ENGINE`. It changes those benchmark copies, preserves their
original files and leaves the copies edited. It does not reset caches, start
Docker containers, measure native Cargo, or measure cold installation.
Each scenario retains one excluded warmup pair. Cargo diagnostic retrieval is
outside the check timers; measured package sets must match the expected affected
crates exactly. Use complete OTel to verify real execution, since cached stderr
alone cannot prove that Cargo reran. See the
[stored-toolchain experiment](stored-toolchain-results.md) for the retained
positive exact-hit result, noise-scale edit results, and design limitations.

Analyze `library-repair.wcprof` with the separately maintained wcprof analyzer.
The in-tree README's `go run ./cmd/wcprof-analyze` command is stale: the analyzer
was removed in e3b4e9c820. The last public analyzer can be extracted from that
commit's parent for diagnostic use, but label that fallback and do not treat its
counterfactual estimates as measured savings.

Check event drops and unresolved waits before interpreting critical-path
rankings. Validate optimization hypotheses with paired unprofiled runs. Preserve
engine image/binary identity alongside results when changing deployments.

For a CLI-only change, `compare-cli.py --before /path/to/before --after
/path/to/after --workdir /path/to/workspace --samples 30 -- check rust:check`
alternates two binaries against the same workspace and records whole-process
timings. It deliberately shares cache history and does not test invalidation.
See [the Unicode-table startup report](cli-startup-width-results.md) for a
matched example, profiler coverage boundaries and correctness checks.
`--before-workdir` and `--after-workdir` can instead compare module settings
in two prepared workspaces using the same binary. Verify equivalent sources
first; this still tests exact warm invocation, not edited-source performance.

The [engine-discovery comparison](engine-discovery-results.md) measures a
CLI-only name-filtering change with the image-managed driver. Its 163ms paired
gain is specifically for `cleanup=false` exact-name discovery; default cleanup
must still discover old engines. The report also retains a separate real-edit
and external-dependency validation, complete profiler gates, and raw samples.

Remaining coverage: additional real repositories and dependency versions,
Clippy/tests/fmt, artifact generation/export, cold installation, concurrent CLI
calls, remote engines and macOS. This fixture cannot establish those claims.

## External Rust dependency upgrade

Add `--dependency-upgrade` with the pinned ripgrep checkout to start with the
application's direct bstr dependency pinned to 1.12.0, then change Cargo.toml and
Cargo.lock to 1.13.0 after the ordinary edit loop. The fixture baseline patch was
generated by `cargo update --package bstr --precise 1.12.0` in the pinned Rust
image. All other package versions stay identical. Cargo resolution is already
represented by the edited lockfile; downloading, unpacking and checking the new
crate version happen within the measured check.

Each invocation performs one first-use dependency upgrade with a unique target
cache namespace. Repeat the whole invocation for independent upgrade samples;
`--samples` controls only the preceding ordinary edit loops. Alternate
`--dependency-first native` and `--dependency-first dagger` between runs. The
immediate `dependency-followup` row is a separate exact-source scenario.

The harness asserts that both sides check bstr 1.13.0, report the same rebuilt
package set, keep the unrelated memchr crate cached, and leave locked inputs
unchanged. It preserves `dependency-upgrade.diff` and `dependency-rebuilds.json`.
This is an application library-version upgrade, distinct from modifying the
source of a workspace library. An already cached action's Cargo diagnostic log
records its producer execution; it is not evidence that a followup reran Cargo.

Add `--profile-dependency-upgrade` on a separate diagnostic invocation to capture
`dependency-upgrade.wcprof`. Its Dagger timing has `profiled=True` in timings.csv;
keep it separate from unprofiled comparisons. `processes.jsonl` records the full
wall-clock boundaries and monotonic duration of every command.

With local OTel capture enabled as described in the telemetry-capture skill,
extract that one CLI trace and account for time outside its root span:

```sh
python3 hack/bench-rust-loop/profile-command.py \
  --processes /tmp/RUN/processes.jsonl --label dependency-upgrade-dagger \
  --otel /tmp/telemetry.jsonl --output /tmp/dependency-upgrade-trace.jsonl
wcprof-otel-analyze /tmp/dependency-upgrade-trace.jsonl
```

The extractor requires exactly one completed CLI root inside the process
interval. It preserves all records for that trace and refuses to overwrite an
existing capture. The wcprof structural gate still needs to pass before using
its ranking. Analytics opt-outs and export configuration must be recorded when
comparing runs; timings with `DO_NOT_TRACK=1` are not default-analytics timings.

For shell-level attribution, add `--trace-phases`. The action prints
`RUST_BENCH_PHASE_NS sync=... cargo=...` to stderr, using three GNU date probes
around the existing rsync and Cargo commands. Both commands remain in one
execution with the same locked caches, and a failed command preserves its
failure status. This diagnostic changes the action and adds probe overhead;
its Dagger rows are marked `profiled=True` and metadata records the shell
instrumentation separately from the native wcprof flag. Use a separate run for
ordinary timings. Phase lines returned on exact hits describe the producer's
earlier execution, not a repeated sync or compile.

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
