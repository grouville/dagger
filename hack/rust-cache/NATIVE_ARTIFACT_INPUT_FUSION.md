# Filter compiler artifacts during their final copy

The [Rust module change `3cd40e5`](https://github.com/grouville/dagger-rust/commit/3cd40e5928563ade3ea1cd21ab9924cd03d88fc3) removes one complete artifact copy before compiling an edited crate. Two eight-pair comparisons reduce the wide 1,026-crate edited-check median from **1.540 to 1.467 s** and **1.579 to 1.510 s**. The pooled median paired saving is **60 ms**, with 10/16 pairs faster. This is a modest improvement, not a claim that every edit gets faster.

Use it as the next experimental native-cache baseline, following `f73c561`. It removes measured work with a small private change, preserves existing caches, and shows no repeated small-workspace latency regression. The native backend remains opt-in; registry dependencies, general build scripts, procedural macros and remote automatic discovery remain unfinished. The complete Cargo +0.5-second target is still unmet.

## The repeated work

An edited batch starts from retained compiler artifacts. The previous path first copies those artifacts into a new directory while excluding the outputs about to be rebuilt. It then copies that filtered directory into the worker's `target` input. At 1,026 crates, both copies traverse the retained artifacts even though only two compiler actions are missing.

The candidate carries the same exclusion list to the final `WithDirectory("target", ...)` call. That applies the filter during placement, removing the intermediate directory. Artifact overlays still apply before filtering. A fully cached reversion keeps its existing path, and non-batch replay retains the previous filtering path. A batch with no hits still starts from an empty artifact directory.

Only `compiler/replay/history.go` and `compiler/replay/batch.go` change: 16 inserted and eight removed lines, including Go's field alignment. There is one additional private slice, no new API, lock or dependency, and no cache-format, compiler-key, worker or incremental-seed-policy change. All fourteen worker build inputs, `main.dang` and the compiler entrypoint are byte-identical to the baseline. This does not introduce the filesystem ancestry or compaction policy from the earlier branching experiment.

## Profile the active path first

Three baseline captures record CPU in both the CLI and engine, CLI runtime traces, wcprof, heap counters and two engine goroutine samples. All commands edit a used source value. The engine has no containerd collection overlap in these captures; none contains a Go GC cycle. These are diagnostic observations, not latency benchmark samples.

The profiles distinguish client filesystem walking from the engine's lower-filesystem walk and directory copying. In one capture, source import occupies about 211 ms of the reported critical path, while directory-copy operations account for about 122 ms elsewhere in the helper's preparation. These scopes must not be added to the broad `dang.invoke` interval, which includes nested work and waits.

Selecting two root-level toolchain files was investigated first. The measured engine and upstream main `717589c9cc` already contain prefix pruning; that suspected missing optimization was rejected. The expensive operations are instead two consecutive copies in compiler-input preparation.

Three candidate captures confirm that five directory-copy operations become four:

| Diagnostic captures | Copies per command | Total recorded copy time |
| --- | ---: | ---: |
| Baseline | 5 / 5 / 5 | 108 / 122 / 116 ms |
| Candidate | 4 / 4 / 4 | 67 / 67 / 61 ms |

Every wcprof capture has zero dropped events and open operations. The final candidate capture contains a Go GC cycle and remains included. Profiling, CPU-profiler shutdown and stack captures affect latency; these times establish work removal, not another complete-command saving.

## Complete edited commands

Both modules use the same owned engine (`e174ad0a…`), source-import snapshot seeds, compact scalar restoration, batch metadata reuse and attribute-array decoder. Telemetry remains enabled against the same local receiver. The containerd root experiment is off, ordinary collection is enabled, and no scratch snapshots, forced collections or forced Go GC are introduced. Wcprof and CPU profiling are off during timing.

Each workload uses one physical source tree and native-cache history shared by the two implementations. Each observation switches the module address, makes a fresh used-source edit and starts a new CLI/helper process. The compiler and engine are warm after one preparation round. Cargo uses Rust 1.77.2, incremental compilation and eight workers, with its target directory outside the imported source. Cargo checks verify that the leaf edit recompiles exactly two crates. Small-workspace controls execute tests.

| Cohort and workload | Baseline median | Candidate median | Cargo median | Median paired saving | Faster pairs |
| --- | ---: | ---: | ---: | ---: | ---: |
| Initial, 1,026-crate check | 1.540 s | 1.467 s | 0.781 s | 52 ms | 5/8 |
| Confirmation, 1,026-crate check | 1.579 s | 1.510 s | 0.781 s | 69 ms | 5/8 |
| Initial, direct 130-crate check | 0.636 s | 0.629 s | 0.128 s | 2 ms | 4/8 |
| Initial, small workspace tests | 0.979 s | 0.993 s | 0.502 s | −16 ms | 3/8 |
| Confirmation, small workspace tests | 1.001 s | 0.988 s | 0.504 s | 1 ms | 4/8 |

The confirmation reverses case order. Column-median differences and medians of paired differences measure different things. The small-test penalty does not repeat; the controls establish no general small-workspace speedup. Wide checks allocate fewer bytes in 14/16 pairs, with median paired savings of 11.4 MB and 4.0 MB across the cohorts. Engine CPU column medians also decrease in both cohorts, but paired CPU improves in only 5/8 and 4/8 observations.

Admission requires no active sessions, a quiet one-second window, host/engine I/O pressure below 5%/1%, host CPU pressure below 10% and engine CPU below 0.1 CPU-seconds per second. Every admitted observation remains included. Maximum host I/O pressure during wide checks is 2.1% initially and 5.2% in confirmation; the first direct-control series reaches 36.6%. Go GC occurs during some commands, with counts retained per arm. No samples are filtered afterward.

## Correctness and cache compatibility

The model, replay and worker suites pass with the race detector. The existing real Rust integration test checks executable output and exact compiler reuse across initial compilation, a middle dependency edit, entirely cached reversion, an app edit, a mix of old dependency output with a new compilation, and another cached reversion. It passes normally and with a unique source comment that prevents previous worker execution hits from masking a broken input copy. No implementation-shaped unit test is added solely to inspect the new private field.

The actual module also passes a fresh 130-action cache, full reuse, a used-source edit with 128 hits, invalid Rust, repair and reversion, with real snapshot collection after every phase. The six retained histories recover 130/130, 1,026/1,026 and 6/6 actions in both physical histories through the candidate module.

The first retained-history probe reports only 2/6 small-workspace hits. The timed series' final case was Cargo, which edited the shared physical source after the last Dagger command. The probe correctly compiled the four unseen actions. Repeating the unchanged probe recovers all six, and the complete six-history check passes. The original failure is retained as harness evidence rather than removed or counted as a passing first attempt.

The experiment is pushed to the Rust-module fork; no PR is opened. It is separate from the six prepared Dagger proposals and the containerd draft. [Exact sources, measurements, profiles and validation logs](experiments/artifact-input-fusion/) include all slower observations and the setup failure. Executable binaries are excluded.

The next useful targets remain source import and repeated helper work, including package discovery. The result narrows the ordinary-command gap but does not finish the native Rust-cache project.
