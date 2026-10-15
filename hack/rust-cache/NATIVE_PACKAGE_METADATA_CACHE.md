# Reuse package discovery across Rust content edits

The [Rust module prototype](https://github.com/grouville/dagger-rust/commit/f3941c1) retains workspace package names separately from compiler results. On warm edited checks at 1,026 crates, it saves 527 ms per pair in the first cohort and 720 ms after swapping histories. Fifteen of sixteen pairs improve. The direct check, which does not discover packages, shows a roughly 20 ms paired penalty in both cohorts. Keep this branch isolated while evaluating its added complexity and that control result. No PR is open.

## What is cached

`cargo metadata --no-deps` reports workspace members. The existing `packages` method reruns it with the whole source directory as an input after a Rust edit. [Cargo documents the workspace-only behavior](https://doc.rust-lang.org/cargo/commands/cargo-metadata.html).

The experiment stores only package names and their validation fields in a native immutable Dagger File. The existing experimental native-cache hint index selects the latest file within the module/project namespace. A hit returns names paired with the current source Directory; it does not return an old `Packages` object or a compilation result.

Validation compares the configured toolchain container ID, locked mode and a workspace fingerprint. One execution hashes names, entry kinds, permissions, owners and link destinations, together with all non-`.rs` file contents. A non-Rust symlink to a file is hashed through its target too, so a `Cargo.toml` link to a `.rs`-named manifest still invalidates correctly. Rust source contents are excluded; adding/removing targets, changing a link, or changing a manifest invalidates discovery. Only successful Cargo discovery publishes new names.

This is enabled only for the experimental `nativeCache` path. A project containing `.cargo` uses the original Cargo discovery path, since that configuration can refer to additional files or source-based tools. Missing or unsupported fingerprint utilities also produce a discovery miss. Legacy compiler behavior is unchanged. Compiler helper/worker inputs are byte-identical to module `30600fd`; the code change is confined to `main.dang`.

The fingerprint is deliberately a prototype. It adds a process on each Rust edit, reads non-Rust resources conservatively, depends on standard shell/find/checksum utilities, and preserves traversal order rather than defining a canonical directory encoding. A different traversal order can cause an unnecessary miss. The current scope does not establish correctness for arbitrary customized Cargo implementations or image configuration that reads Rust source contents during discovery. A native filesystem fingerprint or recorded dependency set needs a clearer general contract before adopting this for the official module.

## Verification

Fourteen independent Cargo comparisons check cold discovery, Rust content edits, new targets, renamed packages, lockfile edits, symlinked manifests, changed manifest-link contents, source links and retargeting, project-configuration fallback and invalid manifests. Results match native Cargo. Wcprof also verifies actual executions: cold or changed metadata runs fingerprinting and Cargo; a content-only Rust edit runs just fingerprinting. Every capture has zero dropped events and no open operations.

An ordinary native check succeeds, compiles a new Rust edit, rejects invalid Rust even with cached names, and succeeds after repair. After the benchmark cohorts and profiles, both histories reuse every compiled action: 130/130, 1,026/1,026 and 6/6. Unchanged runs are correctness checks only.

An archived ordinary-check setup failure ran from the Dagger repository rather than its isolated fixture. It is excluded from measurements.

## Complete edited commands

Both variants use the same warm engine, buffered CLI, selected attribute-array decoder and per-batch telemetry metadata reuse. Wcprof and diagnostic counters are off. Source-import snapshot seeds are off. Each invocation edits a used Rust value. Order rotates; the confirmation swaps physical cache histories. Cargo uses Rust 1.77.2 and incremental compilation. Every expanded listing must contain exactly the expected 1,026-package set.

Both arms send full telemetry to the same local `otlpdump` process writing `/dev/null`. It still receives, decodes and JSON-encodes the records. This removes capture-file writes from the comparison, not telemetry support from Dagger.

Eight initial pairs:

| Command | Original median | Candidate median | Cargo median | Median paired saving | Faster pairs |
| --- | ---: | ---: | ---: | ---: | ---: |
| Direct check, 130 crates | 0.713 s | 0.715 s | 0.126 s | −20 ms | 2/8 |
| List, 1,026 packages | 4.447 s | 4.159 s | 0.466 s | 141 ms | 4/8 |
| Grouped check, 1,026 crates | 2.642 s | 2.029 s | 0.816 s | 527 ms | 8/8 |
| Small workspace tests | 1.203 s | 1.083 s | 0.513 s | 178 ms | 6/8 |

Eight confirmation pairs with histories swapped:

| Command | Original median | Candidate median | Cargo median | Median paired saving | Faster pairs |
| --- | ---: | ---: | ---: | ---: | ---: |
| Direct check, 130 crates | 0.755 s | 0.776 s | 0.129 s | −22 ms | 3/8 |
| Grouped check, 1,026 crates | 3.295 s | 2.287 s | 0.826 s | 720 ms | 7/8 |
| Small workspace tests | 1.251 s | 1.190 s | 0.516 s | 104 ms | 6/8 |

All observations remain included. Admission requires an idle engine and a one-second low-I/O window before each invocation; there is no filtering afterward. Maximum host/engine I/O pressure reaches 11%/17% in the first cohort and 60%/26% in the confirmation. The slowest confirmation check takes 7.49 seconds. The repeated check improvement is useful evidence, but absolute timings remain host-sensitive. The direct control penalty remains unresolved, and the overall Cargo +0.5-second target is still unmet.

Container-cgroup CPU medians for the large check decrease from 2.141 to 2.003 seconds in the first cohort and 2.172 to 1.879 in the confirmation. Lower CPU occurs in six and seven of eight pairs respectively. These counters measure charged cgroup work during the command, not just one function. Listing and small-test CPU results do not show a consistent improvement.

## Recorder calibration

A separate four-pair comparison uses module `30600fd` in both arms and the same receiver binary, changing only file output versus `/dev/null`. Listing paired savings are 198 ms with two of four wins; checks are 36 ms slower with only one of four wins. Maximum host/engine I/O pressure reaches 51%/29%. This does not establish a stable recording penalty to subtract from prior timings, nor diagnose the earlier long outliers. The original recorder and its 62.55 GB capture remain intact.

## Remaining work

A fresh candidate check profile places `Rust.packages` at 244 ms, compared with 688 ms in the preceding baseline capture. This comparison identifies the removed work rather than estimating a new median speedup. Source import remains about 444 ms, and the subsequent `Check.sync` takes about 1.09 seconds. `dang.invoke` includes nested API waits and execution, not only interpreter CPU. The candidate trace has zero dropped/open operations.

The direct-check profile does not explain the approximately 20 ms control penalty: it contains no package-discovery call. Investigate module schema decoding and matched control traces before selecting the implementation. Next work should also replace the fingerprint process with native operations if the simpler input contract can be proved, investigate the remaining helper/API work, and finish storage/transfer checks for source-import snapshots. Registry dependencies, general build scripts, procedural macros and remote automatic state discovery remain unfinished for the native backend.

Evidence and local harnesses: [package-metadata-cache](experiments/package-metadata-cache/). Raw CLI runtime traces remain under `/tmp/rust-cache-sipsma-review/package-metadata-edited-check-profile`.
