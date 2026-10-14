# Procedural macro inputs

Enabling `proc-macro` crate types alone would make the per-crate cache unsafe.
A real fixture reads `data/value.txt` at compile time, outside its consuming
crate. That file is absent from rustc's dep-info. A second case uses an override
file only when it exists; the failed existence check is also absent.

This is normal macro behavior: procedural macros have the compiler's file
access, as described in the [Rust Reference](https://doc.rust-lang.org/stable/reference/procedural-macros.html).
The current native module still rejects procedural macros. No macro result
reuse is enabled by this study.

## Standalone reproduction

The fixture has no registry dependencies. Its test expects the generated value
to be 10. After warming Cargo, change the data to 12 without editing Rust source:
the tests still pass using the old compiled result. Clean the application and
run again: the test correctly fails with 12. Adding a previously absent override
file produces the same stale-success/clean-failure result.

```sh
python3 hack/rust-cache/proc_macro_inputs.py \
  --out /tmp/proc-macro-input-repro \
  --toolchain /path/to/rust/toolchain/bin
```

The checked-in reproduction passes with the pinned Rust 1.77 toolchain used by
our cache fixtures. Logs preserve dep-info and both outcomes. Cargo's missing
tracking is evidence of the challenge, not a reason to reproduce stale results
in Dagger. A source edit that forces rustc also observes the changed file.

## Compare recording mechanisms

`strace` confirms the hidden read. Six alternating edited Cargo pairs give a
median of 0.211 s without tracing and 0.768 s while tracing Cargo's file
syscalls. Tracing only rustc gives 0.234→0.745 s in another six-pair series.
This is too much overhead for the intended development workflow. These are
local Cargo measurements, not edited native-module speedups.

A temporary kernel probe records rustc `openat` and `statx` entry/exit events
without stopping the compiler for each syscall. Eight alternating pairs run
the same fixture in fresh Dagger executions with telemetry enabled. Probe
attachment and readiness happen before timing; each action has a unique source
edit and nonce. The image and engine are warm, while each execution builds into
a fresh target directory. This measures recording cost on fresh compilation,
not native incremental cache performance.

| Complete diagnostic command | Median |
| --- | ---: |
| Probe disabled | 0.651 s |
| Probe enabled | 0.656 s |

The median paired overhead is 9.8 ms; six of eight enabled samples are slower.
Maximum CPU/I/O stalls are 3.1%/2.6%. Every enabled capture records three data-file
opens and three failed override checks, with no reported lost events. Setup
and dependency processing are excluded. This supports investigating kernel
recording further; it does not establish a production overhead bound.

The [saved probe](experiments/compiler-file-probe/file-access.bt) is diagnostic
only. It filters by process name, truncates paths at 256 bytes and handles just
two syscall families. A production cache cannot use its output as-is.

## Requirements before enabling native reuse

The missing inputs must become part of each affected compiler result's native
cache identity, alongside source and dependency hashes. Successful file reads
require contents and relevant metadata; failed lookups require absence; directory
enumeration requires the observed directory entries. Tracking must include
child processes, relative paths, directory descriptors, symlinks and the actual
mount namespace. Lost, truncated or incomplete events must prevent exact-result
reuse. Process-name filtering cannot establish execution ownership.

The existing engine file tracer is for filesystem diagnostics, not this
purpose: it logs selected mount/stat operations and has a 128-byte path buffer.
Landlock alone is insufficient because it does not restrict stat/access-family
queries. See the [kernel documentation](https://docs.kernel.org/userspace-api/landlock.html).

We must also verify how transferred incremental state behaves when a macro's
hidden inputs change. A complete input recorder would make general procedural
macros and build scripts possible without forcing all workspace crates to rebuild
on every unrelated edit. That recorder and native macro support remain unfinished.

Artifacts are under `/tmp/rust-cache-sipsma-review/proc-macro-hidden-input`,
`proc-macro-hidden-input-standalone`, `proc-macro-trace-overhead`,
`proc-macro-selective-overhead` and `proc-macro-bpf-probe`. The temporary probe
processes and tracefs mounts were removed after measurement. No upstream PR was
opened and no engine execution semantics changed.
