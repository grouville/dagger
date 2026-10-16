# Native package discovery on the current compiler baseline

Selection update: the [subsequent current-engine comparison](NATIVE_DISCOVERY_SELECTED.md) does not reproduce the earlier direct-control penalty and selects `da1ae47` for following experiments. This page preserves the original measurements and decision at that time.

The isolated Rust-module experiment [da1ae47](https://github.com/grouville/dagger-rust/commit/da1ae47b6c96a3117de303b7584d028e35166530) replaces the package-discovery fingerprint process with the existing experimental `Directory.treeFingerprint` operation. Across two eight-pair cohorts, edited 1,026-crate checks save **101 ms per pair**, with **14/16 faster pairs**. Small workspace tests save **33 ms**, with **12/16 faster pairs**. The direct-check control is **13 ms slower per pair** overall, despite never invoking package discovery; that discrepancy remains unresolved. The experiment stays separate from the selected `3cd40e5` baseline.

The large check remains about **0.60 seconds slower than Cargo**, outside the Cargo +0.5-second target. Expanded listings still take about 3.6 seconds. This is a narrower result than a general module or collection speedup.

## Change and compatibility

The before revision is [3cd40e5](https://github.com/grouville/dagger-rust/commit/3cd40e5928563ade3ea1cd21ab9924cd03d88fc3), including the selected artifact-input fusion. Only `main.dang` changes: five lines added and 34 removed. The complete `compiler/` Git tree is identical, including the worker, result-key construction, incremental seed selection and dependency files. No engine rebuild or compiler cache-format change is involved.

The old path starts a shell process to hash the source layout and non-Rust contents before looking up retained package names. The candidate calls the buffered native filesystem operation already installed in the measured engine. It hashes paths, entry kinds, permissions, ownership, supported xattrs and non-Rust contents. Rust content edits preserve the discovery fingerprint; adding a target or changing a manifest invalidates it. Symlinks, special files and `.cargo` paths return no fingerprint and use Cargo metadata directly. The retained hint also checks the configured toolchain identity and `locked` setting. A separate hint namespace prevents interpreting old shell fingerprints as native ones.

This remains an opt-in native-cache experiment requiring experimental engine APIs. The general contract for custom Cargo implementations that inspect Rust contents is not established. Registry dependencies, build scripts, procedural macros and remote cache discovery remain unfinished parts of the wider project.

## Complete edited commands

Every arm edits a Rust value before starting a fresh process. The engine, toolchain and compiler history are warm. Both implementations and Cargo use the same physical source for each workload. Telemetry stays enabled with the local decoding/null receiver. The engine binary, source snapshot seeds, batch metadata reuse, attribute decoder and scalar restoration settings are identical between arms. Wcprof is off during timing; ordinary snapshot collection and Go GC remain enabled, with no forced collection or added scratch snapshots.

The confirmation reverses each case order. Cargo uses incremental Rust 1.77.2 with eight workers and a target directory outside the imported source. Leaf checks assert exactly two Cargo compilation actions. Listings assert all 1,026 expected package names. All 192 admitted measured commands are retained, plus their preparation runs, CPU/heap counters, pressure and logs.

| Cohort and command | Shell median | Native median | Cargo median | Median paired saving | Faster pairs |
| --- | ---: | ---: | ---: | ---: | ---: |
| Initial, 1,026-crate collection check | 1.431 s | 1.356 s | 0.779 s | 90 ms | 6/8 |
| Confirmation, same check | 1.586 s | 1.371 s | 0.771 s | 204 ms | 8/8 |
| Initial, 130-crate direct check | 0.600 s | 0.623 s | 0.123 s | -20 ms | 1/8 |
| Confirmation, same direct check | 0.611 s | 0.609 s | 0.128 s | -4 ms | 3/8 |
| Initial, small workspace tests | 0.964 s | 0.940 s | 0.494 s | 33 ms | 6/8 |
| Confirmation, same tests | 0.983 s | 0.957 s | 0.498 s | 44 ms | 6/8 |
| Initial, expanded package listing | 3.754 s | 3.585 s | 0.445 s | 16 ms | 5/8 |
| Confirmation, same listing | 3.780 s | 3.587 s | 0.436 s | 111 ms | 8/8 |

The pooled paired listing saving is 86 ms, with 13/16 faster pairs. Its engine CPU does not improve consistently: median paired CPU use increases by about 0.26 CPU-seconds. The pooled direct-check penalty is 13 ms, with only 4/16 faster pairs, while paired engine CPU and allocated bytes are approximately unchanged. These controls prevent claiming a benefit across all commands.

One confirmation baseline check overlaps ordinary snapshot collection and takes 3.109 seconds; it remains included. No initial measured command overlaps collection. All listing commands include a Go GC cycle. Maximum post-admission host I/O pressure is 45.5% in the direct control and 4.4% in the large confirmation checks; listing CPU pressure reaches about 30%. Admission does not guarantee a quiet complete command. These observations are retained rather than explained away.

## Correctness and preserved cache reuse

Sixteen discovery cases match `cargo metadata --no-deps`: cold discovery, a non-workspace path dependency, Rust edits, a new target, package renaming, lockfile changes, manifest and source symlinks, retargeted links, Cargo configuration, and malformed manifests. The inspector verifies both names and actual execution counts. A Rust content edit requires no discovery execution; unsupported trees run Cargo. The final malformed workspace manifest fails in both implementations. All final wcprof captures have zero dropped events and open operations.

Ordinary collection checks also pass through cold compilation, an edit, invalid Rust, repair and reversion. Invalid Rust fails instead of reusing a successful check. Independent inspections then require **2/2 compiled-result hits** after each successful stage, including a direct check. The unchanged calls establish correctness, not a performance claim.

All six retained histories also pass strict reuse through the candidate: **130/130, 1,026/1,026 and 6/6 in each physical history**. The validation first prepares the current input explicitly: a benchmark's last Cargo or listing edit may not have been compiled by Dagger. It then requires complete reuse without relaxing expected hit counts.

The archive preserves initial harness failures. The first trace drain encountered a still-open GC operation; the final recorder disables new global recording, drains the existing recorder and preserves every chunk. Another oracle expectation incorrectly assumed an excluded dependency manifest would make `metadata --no-deps` fail. The initial ordinary-check fixture imported tens of thousands of files and was interrupted: it inherited the ambient `/tmp/.git`, so its absolute default path correctly resolved to `/tmp`. A small Directory probe confirms that behavior; adding a local Git boundary resolves the same argument inside the fixture. This is a test-layout error, not an engine defect. Later inspections incorrectly required a current batch after reversion, although restored results can be assembled from older snapshots without one. The final assertions preserve exact compiler action/hit counts and check batch execution counts only where a current batch exists.

## What the profiles establish next

Twelve diagnostic captures cover both implementations and two case orders for the large check, direct check and listing. Each includes engine/CLI CPU profiles, a CLI runtime trace, wcprof and bounded goroutine captures. They are separate from benchmark timing, and all complete without dropped events or open operations.

Large-check discovery falls from **230/291 ms to 143/132 ms**. The native filesystem operation takes **79/74 ms**. Checks start two executions instead of three; listings start none instead of one. Direct checks never call the new fingerprint operation. One slower native direct capture spends 656 ms in the worker execution, versus 329 ms in its counterpart; this locates variation in that diagnostic capture, without proving the cause of the unprofiled control penalty.

Expanded listings still allocate about **3 GB per command**. One wcprof capture records 13,674 result publications and 3,078 requests for each dimension-key field. Its reported 2.38-second critical path assigns about 750 ms to result publication, 439 ms to artifact items and 419 ms to host-directory work. These are scopes within the trace, not extra durations to add to command time.

Two native listing CPU captures contain 16.30 and 15.79 CPU-seconds over five-second windows. Stored protobuf-JSON decoding accounts for about 23% and 22% cumulatively; span conversion accounts for about 20% in both. These frames overlap, and the windows include background work. The existing direct-span prototype already targets part of this conversion; it must not be presented as a new discovery or enabled on the strength of these profiles alone. The next useful experiments should reduce repeated publication or serialization work and test complete commands with telemetry preserved.

[Raw evidence, exact sources, scripts and validation](experiments/native-discovery-current/). No new upstream PR is opened; the [prepared Dagger proposals](upstream-prs/README.md) and containerd draft remain separate.
