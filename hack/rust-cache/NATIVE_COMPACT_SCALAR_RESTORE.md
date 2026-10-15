# Keep restored builtin scalar lists compact

The [standalone engine change](https://github.com/grouville/dagger/compare/a5c17bb7e...376e7c324) removes repeated call copies when loading plain scalar lists from cache. On the accumulated benchmark engine, switching the same final binary between readers changes retained sampled heap from **5.2 to 2.8 GiB** and live objects from **33.2 to 15.5 million**. Native compiler results remain reusable. No PR is open. The native Rust edited-command latency target remains unmet.

## Change and correctness

The old reader creates a detached result and deep-copies the producing call for every inline scalar. A list of N values whose call contains M arguments therefore does O(N×M) call-copy work. The new representation keeps plain scalar values and one independent recorded call; an element's result is created when requested. Reading the array takes O(N+M) call-copy work, in addition to parsing its scalar payloads.

Only non-null builtin scalar elements without attached identities, resources or offers qualify. Nullable, custom, referenced and resource-bearing elements keep the general decoder. Invalid payloads retain its validation and error messages. The new representation preserves the recorded element calls even if a consumer supplies no call or another one, and it retains independent call ownership. It reuses `DynamicArrayOutput` value serialization and field assignment. The private in-memory representation changes; one existing nested-list test now uses `Enumerable` for its plain leaf while preserving value/identity assertions.

Saving the new representation reads plain values directly; otherwise it would recreate the expensive calls at shutdown. Snapshot-owner traversal also skips these closed builtin values. There is no new lock, dependency, global production cache, diagnostic flag or persistence format. The existing version-5 envelopes are unchanged.

The full `dagql` package passes under `-race` after both restore and save changes (67.727 s). Regressions cover exact values and large numbers, element call identity, ownership after caller/child mutation, nil-frame access, assignment, bounds, repeated restores, identical saved envelopes, invalid versions/payloads and per-item session resources. Existing tests cover nullable/custom values, references, nested lists, transfers, owners and pruning. A production-source search found the other core uses construct result-backed arrays; the representation assertions in snapshot tests concern object arrays, which retain the old decoder.

The real engine preserves all six native histories before and after edited workloads and after switching back to its legacy reader: both histories reuse 130/130, 1,026/1,026 and 6/6 compiler actions. The legacy reader successfully loads data saved by the compact implementation. Artifacts and incremental state remain native Dagger snapshots.

## Component and retained-memory measurements

Five fresh-process pairs use Go 1.26.6, GOMAXPROCS=8, rotating order, fixed quiet admission and 300 ms per benchmark. The comparison overlays the unmodified main decoder and owner walker. Each fixture has N strings and N literal path arguments; this deliberately exercises the observed repeated-copy shape. Save timing starts from an already-restored value. These are construction/allocation results, not Rust-command speedups.

| Operation | Values / call arguments | Main | Compact | Main / compact allocated bytes | Main / compact allocations |
| --- | ---: | ---: | ---: | ---: | ---: |
| Restore | 128 / 128 | 1.941 ms | 0.173 ms | 3,867,413 / 373,179 | 19,214 / 1,301 |
| Restore | 512 / 512 | 24.905 ms | 0.687 ms | 55,115,129 / 1,487,545 | 273,422 / 5,141 |
| Restore | 1024 / 1024 | 111.998 ms | 1.354 ms | 215,609,968 / 2,972,090 | 1,071,118 / 10,261 |
| Save | 128 / 128 | 0.134 ms | 0.071 ms | 96,089 / 39,756 | 1,157 / 517 |
| Save | 512 / 512 | 0.514 ms | 0.277 ms | 381,136 / 155,924 | 4,613 / 2,053 |
| Save | 1024 / 1024 | 1.164 ms | 0.548 ms | 762,053 / 311,661 | 9,221 / 4,102 |

Heap captures run outside latency intervals, without active clients and after diagnostic Go collection. The engine has no Docker memory limit. The same persisted volume survives every graceful restart; its dataset can grow or compact, so the reversal and allocation stacks matter more than treating the snapshots as an exact census. These are sampled Go heap estimates from a long-lived experimental cache, not a claim about a normal project or a leak.

| Reload | Sampled retained heap | Sampled live objects |
| --- | ---: | ---: |
| V1 legacy reader | 5,399 MiB | 34.03 million |
| V2 compact reader | 2,828 MiB | 15.46 million |
| Same V2 binary, legacy reader again | 5,328 MiB | 33.23 million |

The same-V2 reversal is about 47% fewer retained bytes and 53% fewer objects with compact reading. In the legacy reader, detached scalar results and cloned calls account for about 2.4 GiB cumulatively. That expansion disappears from the main retained allocation stacks in compact mode; scalar-array decoding retains about 104 MiB cumulatively. Frames overlap and must not be added.

## Complete edited commands

Each process gets two warm-up passes followed by eight admitted measurements per workload. Every invocation edits a used Rust value. The CLI, Rust module `cd6d25e`, source history, compiler image, telemetry and native cache key are unchanged. Listings must contain the exact 1,026 package names. Cargo uses Rust 1.77.2, incremental compilation, eight workers and locked/offline workspace checks. Batch telemetry metadata reuse and the selected attribute decoder stay on; direct span-protobuf conversion, source-import snapshot seeds and snapshot notifications stay off. Wcprof and diagnostic counters are off during timing.

Admission requires an idle engine, a one-second quiet window, host/engine I/O stalls below 5%/1%, host CPU stall below 10%, engine CPU below 0.05 CPU-seconds/second, and a maximum wait of 60 seconds. Admitted observations are never filtered afterward. These are separate process cohorts, not paired old/new command measurements. The first V1 control predates completion of saving the new representation; its disabled path does not construct that representation. The subsequent two cohorts use the same final V2 binary.

| Process cohort | Listing: Dagger / Cargo | Edited check: Dagger / Cargo |
| --- | ---: | ---: |
| V1 control | 3.613 / 0.446 s | 2.039 / 0.821 s |
| V2 compact | 4.135 / 0.460 s | 1.906 / 0.812 s |
| V2 control confirmation | 4.247 / 0.476 s | 2.328 / 0.914 s |

CPU charged to the engine during listing increases from 12.05/13.09 seconds in the two controls to 16.28 seconds in compact mode; the following check decreases from 3.66/3.85 to 1.77 CPU-seconds. Those counters exclude later background work. That difference motivated additional cohorts of edited checks without interleaved listings. It does not by itself identify the cause or prove faster compilation:

| Check-only cohort | Dagger median | Cargo median |
| --- | ---: | ---: |
| V2 legacy reader | 2.225 s | 1.153 s |
| V2 compact reader | 2.281 s | 0.922 s |

The isolated checks do not confirm the apparent improvement in the mixed cohorts: 2.225 versus 2.281 seconds for Dagger while Cargo changes from 1.153 to 0.922 seconds. Across admitted samples, maximum host/engine I/O stalls are 34.2%/1.1% in the initial control, 2.0%/0.2% in compact mode, and 4.7%/0.2% in the same-binary control. Check-only host maxima are 9.1% and 8.0%. All observations remain included. The 10.8-second compact warm-up is retained in the logs and excluded from the fixed eight-sample measured cohort like every warm-up.

## Remaining hot path

A separate fresh edited check takes 1.875 diagnostic seconds. Its complete wcprof capture has 10,830 events, zero dropped events and zero open operations. The longest query takes 1.68 seconds: source import uses about 405 ms, package discovery's invocation about 200 ms and Check.sync about 979 ms. The invocation includes compiler/helper work and API waits, not interpreter CPU alone. These durations describe one capture and are not additional benchmark observations.

The accompanying ten-second Go CPU profile includes 4.91 sampled CPU-seconds, with 2.87 cumulatively in engine cache pruning after session completion, including size accounting. This includes work after the command; it must not be added to the command's elapsed time or confused with Go runtime GC. Repeated cache accounting is a concrete next investigation. The earlier [sparse usage-map allocation change](CACHE_USAGE_ALLOCATIONS.md) is still not installed in this engine. Source import and compiler/helper preparation remain the next latency work; the [native source-import snapshot experiment](NATIVE_SOURCE_IMPORT_SNAPSHOTS.md) still needs its storage/transfer checks.

Memory and decoder-construction improvements are established on these fixtures. Complete-command latency remains sensitive to workload order and host conditions; Cargo itself varies across cohorts. No general edited-command speedup is claimed. The native-Cargo-plus-0.5-second target is still unmet. Registry dependencies, general build scripts, procedural macros and remote automatic state discovery remain separate unfinished work for the native backend.

[Raw samples, admission/pressure records, test logs, local harnesses, exact source manifests and heap profiles](experiments/compact-scalar-restore/).
