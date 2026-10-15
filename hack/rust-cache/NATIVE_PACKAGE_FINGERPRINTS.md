# Package discovery without an extra process

Two isolated experiments follow the [package metadata cache](NATIVE_PACKAGE_METADATA_CACHE.md). Neither is selected as the default, and no PR is open.

The native experiment removes the fingerprint container. In four diagnostic checks, package discovery falls from 225–238 ms to 136–147 ms. Complete edited commands improve most clearly when listing 1,026 packages: paired savings are 542 ms and 705 ms across two eight-pair cohorts. Large edited checks do not show a repeatable latency or CPU benefit. This experiment also removes a script field from the Rust object, so the listing gain cannot be attributed entirely to the native filesystem operation.

A smaller module-only experiment keeps the existing shell algorithm and moves that script into its function. An independent probe confirms that serialized Rust project state shrinks from 2,323 to 1,344 bytes. The 906-byte script is absent from the resulting object; the remaining reduction is its JSON field and escaping. Full-command measurements are noisy, and the confirmation stops at the existing 60-second idle-admission limit. This establishes a concrete state reduction, not a confirmed command speedup.

## Isolated changes

- [Engine experiment: `7ced553fb`](https://github.com/grouville/dagger/commit/7ced553fb) adds `Directory.treeFingerprint(ignoreContents:, reject:)`. It walks an immutable snapshot in sorted path order and hashes paths, permissions, ownership, supported extended attributes and file contents. Timestamps and sizes are excluded; contents still determine the length of ordinary included files. Rust source contents can be excluded without excluding their names or metadata. A symlink, special file or rejected path returns null. Existing filesync hashing and directory digest formats are unchanged.
- [Native module: `e9a9981`](https://github.com/grouville/dagger-rust/commit/e9a9981) uses this operation with `**/*.rs` ignored and `**/.cargo` rejected. Unsupported trees call Cargo directly. Successful discovery still stores only names and validation fields in an immutable Dagger File through the existing experimental hint index. It uses a separate hint namespace from the shell prototype.
- [Module-only experiment: `cd6d25e`](https://github.com/grouville/dagger-rust/commit/cd6d25e) moves `packageFingerprint` from an instance field to a local binding inside `cachedPackageNames`. The shell logic, fingerprint validation, hint namespace and Cargo fallback stay the same. No new engine API is needed for this change.

Both Rust variants change only `main.dang`. Compiler helper, model, worker, module and dependency files remain identical to `f3941c1`. The native backend remains opt-in. The engine API is experimental and has no generated SDK or upstream compatibility claim.

## Correctness

The complete `engine/contenthash` unit package passes with the race detector. Focused tests cover content-only Rust edits, manifest changes, new/removed targets, renames, root/file/directory permissions, empty directories, entry kinds, timestamp independence, canonical creation order, symlink rejection, configuration rejection, invalid patterns and cancellation.

Both module variants pass fourteen comparisons with independent native Cargo results. Each checks cold discovery, content edits, new targets, package renames, lock changes, symlinked manifests and their contents, source links and retargeting, `.cargo` fallback and invalid manifests. Wcprof captures contain no dropped or open operations. The native variant launches no process after an ordinary Rust edit; metadata changes and unsupported trees launch Cargo. The local-script variant preserves the shell prototype's execution counts.

The first native validation used fixtures identical to an earlier run. An expected Cargo execution was already cached. The trace showed a new metadata hint being published, rather than an incorrect name hit. The retained rerun adds a unique manifest comment and namespace, and asserts hint publication as well as actual execution counts. All fourteen cases pass.

Ordinary checks compile fresh edits, reject invalid Rust with cached package names and succeed after repair in both variants. Both histories retain every compiler result after the native engine restart: 130/130, 1,026/1,026 and 6/6. The same strict assertions are repeated after the subsequent experiments.

Two final assertions initially expected full reuse immediately after listing-only source edits. They correctly observed two dirty actions instead: 128/130 and 1,024/1,026. The listings had changed source without compiling it. Those pending edits are compiled explicitly before the final full-reuse check; the initial logs remain archived. Unchanged runs establish correctness only.

The native filesystem operation does not establish correctness for arbitrary customized Cargo implementations that read `.rs` contents while discovering packages. Symlinks and project `.cargo` configuration conservatively use Cargo. General compiler support, remote automatic state discovery and transfer/storage validation remain separate unfinished work.

## Complete edited commands

Both arms use the same warm engine and buffered CLI, with telemetry enabled, the selected array decoder and per-batch telemetry metadata reuse. Both send full telemetry to the same `otlpdump` process, which receives, decodes and JSON-encodes records before writing `/dev/null`. Wcprof and diagnostic counters are off during timing. Source-import snapshot seeds and snapshot-notification changes are off. Cargo uses Rust 1.77.2 with incremental compilation.

Every invocation changes a used Rust value. Command order rotates. The confirmation exchanges physical histories. Listing must return exactly the expected 1,026 names. Admission requires an idle session state and a one-second low-I/O window; all admitted samples remain included. Medians and paired medians answer different questions and are reported separately.

Shell fingerprint versus native filesystem fingerprint, eight pairs:

| Command | Shell median | Native median | Cargo median | Median paired saving | Faster pairs |
| --- | ---: | ---: | ---: | ---: | ---: |
| Direct check, 130 crates | 0.702 s | 0.694 s | 0.132 s | −23 ms | 3/8 |
| List, 1,026 packages | 4.259 s | 3.514 s | 0.459 s | 542 ms | 5/8 |
| Grouped check, 1,026 crates | 1.996 s | 2.091 s | 0.822 s | −125 ms | 3/8 |
| Small workspace tests | 1.140 s | 1.003 s | 0.528 s | 98 ms | 6/8 |

Eight confirmation pairs with histories exchanged:

| Command | Shell median | Native median | Cargo median | Median paired saving | Faster pairs |
| --- | ---: | ---: | ---: | ---: | ---: |
| Direct check, 130 crates | 0.703 s | 0.696 s | 0.127 s | 6 ms | 4/8 |
| List, 1,026 packages | 4.092 s | 3.417 s | 0.455 s | 705 ms | 7/8 |
| Grouped check, 1,026 crates | 1.981 s | 1.966 s | 0.798 s | 35 ms | 4/8 |
| Small workspace tests | 1.022 s | 0.994 s | 0.511 s | 37 ms | 6/8 |

The large check's engine-cgroup CPU medians increase from 1.907 to 3.361 seconds and from 1.860 to 3.486 seconds. The new operation alone does not explain this. Listing CPU medians decrease from 17.472 to 13.301 seconds and 17.596 to 12.021 seconds. Small-test CPU decreases in seven and eight pairs respectively. These are complete-command cgroup counters, including other engine work during that interval.

Maximum host/engine I/O pressure reaches 30%/7% in the first cohort and 9%/6% in the confirmation. The slowest admitted commands take 6.22 and 4.99 seconds respectively. The large-check target of Cargo plus 0.5 seconds remains unmet.

## Isolating the serialized script

The module-only comparison changes no fingerprint algorithm. Its eight initial pairs give:

| Command | Field median | Local median | Cargo median | Median paired saving | Faster pairs |
| --- | ---: | ---: | ---: | ---: | ---: |
| Direct check, 130 crates | 0.960 s | 0.937 s | 0.128 s | 50 ms | 6/8 |
| List, 1,026 packages | 5.969 s | 5.124 s | 0.545 s | 849 ms | 5/8 |
| Grouped check, 1,026 crates | 2.830 s | 3.208 s | 0.831 s | −18 ms | 4/8 |
| Small workspace tests | 1.112 s | 1.344 s | 0.627 s | −21 ms | 4/8 |

This cohort is substantially noisier, including a 10.35-second candidate listing. A follow-up attempts only listing and the direct control; it stops before completing the first measured pair because no low-I/O admission window appears within 60 seconds. Preparation, partial measurements and the failure are retained. There is no confirmation cohort and no claim of a stable command benefit.

Temporary module copies expose `JSON.encode(packages(source: source))` through a root method. Reading the nested `project` object proves that the original contains `packageFingerprint`, while the local-binding variant does not. No probe methods are added to either measured branch. Dang's serialization of private state is intentional; this experiment moves implementation data out of that state. The remaining constant script fields suggest a further module-level opportunity, which is not yet measured.

## What the profiles establish

Four matched diagnostic captures cover both physical histories and both implementations. The native fingerprint takes 67–74 ms; total discovery falls by about 90 ms in each history. Complete profiled commands still vary from 2.03 to 2.92 seconds. Each edited native check launches two compiler executions; the shell variant launches those two plus fingerprinting.

One native capture includes two module-source imports taking 316 and 326 ms, compared with 13 and 22 ms in its shell counterpart. Bounded raw telemetry identifies the imports as the Rust module and its compiler dependency, not extra user workspace imports. A subsequent native capture imports them in roughly 16–19 ms. This is intermittent evidence to investigate, not proof of a persistent module-import regression.

CPU captures show other substantial work, including cache pruning, snapshot garbage collection and, in one baseline capture, Go garbage collection. The filesystem fingerprint accounts for roughly 60 ms of sampled CPU in the relevant native capture. The profiles therefore do not support attributing the repeated additional command CPU entirely to traversal or to Go GC.

Matched direct-check traces normally decode module schemas in about 2 ms for all three module versions. One cold original-module load and one slower native control remain included. These captures do not reproduce the earlier isolated 12 ms schema decode or resolve the previously observed roughly 20 ms direct-control penalty.

The standalone 128-crate filesystem microbenchmark takes about 7.6 ms, allocates about 5.5 MB and performs about 20,100 allocations. Buffer reuse and existing metadata indexes are possible next experiments; neither has a complete-command benefit established here.

The owned engine exits cleanly after 233.784 seconds while persisting its accumulated query cache, then restarts with its volume preserved. This maintenance interval is excluded from warm-command comparisons. No cache is reset to make the new implementation appear faster.

Evidence, raw CPU profiles, compressed wcprof captures and local harnesses: [package-fingerprints](experiments/package-fingerprints/). The original large telemetry file is read only through a bounded 17 MB window and remains intact.
