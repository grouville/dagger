# Select native package discovery for the Rust module

Use Rust-module [da1ae47](https://github.com/grouville/dagger-rust/commit/da1ae47b6c96a3117de303b7584d028e35166530) as the next experimental native baseline. It includes the selected artifact-input fusion and replaces the package-discovery shell process with the existing native directory fingerprint. On the current engine, complete edited checks over 1,026 crates improve from **1.559 to 1.435 seconds** median, with a **130 ms median paired saving**. Cargo takes **0.768 seconds**. The Cargo +0.5-second target remains unmet.

The [earlier discovery comparison](NATIVE_DISCOVERY_CURRENT.md) stayed isolated because its direct-check control was 13 ms slower per pair. A new balanced randomized comparison does not reproduce that penalty: the direct control is 12 ms faster per pair. Its profiles execute no package discovery in either variant. The compiler tree is identical, and switching between module revisions immediately reuses existing compiled results without a preparation step.

## Current comparison

The engine is `4699d50526e3b2c358d0467c6cacc79aff1061b9295754648713a21104524c65`, including the selected [direct dimension-key reads](NATIVE_DIMENSION_KEY_FIELDS.md). Both variants use that same binary and the same controls. The Rust-module before revision is `3cd40e5928563ade3ea1cd21ab9924cd03d88fc3`; the candidate is `da1ae47b6c96a3117de303b7584d028e35166530`. Their `compiler/` Git tree is exactly `0c9e8b107593d1e5a623145c7b004258c192d060`.

Eight pairs per workload use fresh CLI processes and fresh edits to used Rust values. The same physical source and native history serve both variants and Cargo. Engine, toolchain and compiler caches are warm. One preparation round per workload is excluded by design. Telemetry remains enabled through the local receiver. Wcprof is off during timing; ordinary Go GC and snapshot collection remain enabled, with no forced collection.

Each workload gets its own randomized order, balanced at four original-first and four candidate-first pairs. The fixed random seed, exact orders and source-edit values are recorded. This breaks the repeated order pattern that produced uneven Go-GC counts in earlier controls. It does not eliminate timing noise or guarantee a quiet command after admission.

| Complete edited command | Shell median | Native median | Cargo median | Median paired saving | Faster pairs |
| --- | ---: | ---: | ---: | ---: | ---: |
| Collection check, 1,026 crates | 1.559 s | 1.435 s | 0.768 s | 130 ms | 5/8 |
| Direct check, 130 crates | 0.625 s | 0.629 s | 0.130 s | 12 ms | 5/8 |
| Small workspace tests | 0.992 s | 0.951 s | 0.497 s | 37 ms | 7/8 |
| Expanded listing, 1,026 packages | 2.927 s | 2.820 s | 0.443 s | 126 ms | 6/8 |

Column medians and median paired differences differ. The large candidate has one **2.720-second** sample overlapping ordinary snapshot collection; it remains included. All admitted observations are retained. Maximum host CPU/I/O pressure is about 6.5%/4.0% for the large check and 32.7%/3.3% for listings. Listing engine CPU is approximately unchanged: **12.41 versus 12.45 CPU-seconds** median. This change removes a launch and latency, without establishing a listing CPU improvement.

The target is met in **0/8** large checks, **3/8** direct checks and **7/8** small test commands. The paired median Dagger-minus-Cargo gaps are **653 ms**, **503 ms** and **455 ms**, respectively. These are measurements of this fixture set; they do not establish general Cargo parity. Timings from the earlier engine and the current engine are kept separate.

## Mechanism and correctness

The module diff remains five added lines and 34 removed lines in `main.dang`. The native operation fingerprints layout, metadata and non-Rust contents. A Rust content edit preserves the names hint; adding a target or changing a manifest invalidates it. Symlinks, special files and `.cargo` paths use Cargo directly. Toolchain identity and the locked setting remain part of hint validation. A separate hint namespace distinguishes the native hash format from the old shell format.

Six new paired diagnostic captures preserve CPU profiles, CLI runtime traces, wcprof and bounded goroutine snapshots. Every final recorder has zero dropped events and zero open operations.

| Diagnostic path | Shell | Native |
| --- | ---: | ---: |
| Large-check package discovery | 249 ms | 155 ms |
| Large-check container executions | 3 | 2 |
| Listing package discovery | 247 ms | 143 ms |
| Listing container executions | 1 | 0 |
| Direct-check container executions | 2 | 2 |

The native fingerprint itself takes **77 ms** in the large check and **74 ms** in the listing. Both direct captures execute zero fingerprint operations. The large candidate's compiler scope takes 877 ms versus 703 ms in its counterpart, so the whole instrumented candidate command is slightly slower despite faster discovery. Diagnostic durations are excluded from the benchmark cohorts and do not substitute for them.

On a fresh cache namespace, all **16** discovery cases match `cargo metadata --no-deps`: cold input, excluded path dependencies, Rust edits, new targets, renaming, lock edits, linked manifests and sources, link retargeting, configuration fallback and malformed manifests. Unsupported trees actually execute Cargo; ordinary Rust edits reuse the names without a discovery process.

Normal public collection checks pass cold compilation, a used source edit, invalid Rust, repair and reversion. Invalid Rust fails. Inspections require **2/2 compiled-result hits** after every successful stage, including a direct check. A further frozen-source check switches candidate → original → candidate → original: each inspected switch immediately returns **2/2 hits**, without preparing or recompiling the source. The optimization preserves existing backend results across the module revision change.

All six retained histories also pass. Initial inspections preserve **130/130** and **6/6** in both histories, **1,026/1,026** in one large history, and **1,024/1,026** in the large history whose last listing edited two uncompiled actions. After preparing that current input, strict reuse requires every action in all six histories. None of these unchanged inspections is a performance observation.

## Selection and remaining work

The six experimental fixture configurations now point to the native-discovery module. Their before/after configuration contents are archived. [SELECTED_BASELINE.json](SELECTED_BASELINE.json) records the module, engine and common benchmark controls for subsequent work. Direct key-field reads stay enabled; profiling and temporary modes are off, ordinary snapshot collection is enabled, and no clients remain active.

The engine still spends roughly 200 ms importing the large source, and the fingerprint still walks its filesystem. Compiler orchestration and snapshot work remain substantial. Source-import preparation, the fingerprint walk and the snapshot-collection tail are concrete next profiling targets. Registry dependencies, general build scripts, procedural macros and automatic remote state discovery remain unfinished; the native backend remains opt-in and the Rust module's default is unchanged.

The refreshed Sipsma review records his latest twenty PRs. [#14685](https://github.com/dagger/dagger/pull/14685) addresses the full-filesystem shutdown flush observed in earlier engine stops. Its description explicitly trades away the final shutdown durability barrier; it is not applied here, and its expected shutdown savings are not counted as build improvements. The existing [eight Dagger proposals](upstream-prs/README.md) remain ready for individual review, with no new PR opened.

[Raw measurements, correctness checks, profiles and selected configurations](experiments/native-discovery-selected/).
