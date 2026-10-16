# Faster mirror walks do not make edited builds faster

The metadata prototype stays disabled. Its isolated 1,026-crate mirror walk improves **33.8 → 22.9 ms**, but direct import captures leave the time before copying almost unchanged: **145.2 → 143.5 ms**. Complete edited checks show no consistent improvement, and the new filesystem option adds allocated bytes to ordinary walks. The selected engine and module are restored; the upstream batch remains at eight proposals.

## Locate elapsed time before changing code

Ten fresh edits on the selected engine put the median source import at **168.0 ms**: **147.4 ms before the copy span**, **20.0 ms inside it**, and **0.4 ms afterward**. Nine copy spans take 19–22 ms; one takes 251 ms, bringing that import to 399 ms. The slow case is consistent with the bounded snapshot-seed full-copy fallback, but seed depth was not emitted, so that attribution is inferred. All ten observations remain in the evidence.

These are warm-engine and warm-compiler measurements, each with a fresh CLI process and a new used source value. They are not cold-engine results. The normal `copy` span includes checksum, lookup, physical copy, commit and publication; it is not a byte-copy-only timer. Telemetry stays enabled. Streaming updates are deduplicated by trace/span ID, and only valid completed spans are used.

Three separate CPU/wcprof captures locate work in the engine mirror walk and the CLI sender. The engine mirror walk accounts for 330 ms of CPU across the three captures, including 180 ms below metadata loading. The CLI sender walk uses about 100 ms in the first capture. Wcprof places source import on the command's critical path, but these concurrent CPU totals do not establish which walk determines its elapsed time.

## The scoped prototype

The engine-owned mirror walk loads extended attributes through the general filesystem walker. Its comparison ignores those attributes, regular-file reuse reads the stored content digest separately, and the existing filesync hash formatter hashes other metadata. The prototype adds an explicit filesystem option and enables it only for that mirror walk. Host metadata collection and XXH3 hash formatting retain their existing paths.

Six fresh-process component pairs give these medians:

| Mirror fixture | Default walk | Skip unused attributes | Allocated bytes |
| --- | ---: | ---: | ---: |
| 128 crates | 3.98 ms | 2.64 ms | 783 → 491 kB |
| 1,026 crates | 33.83 ms | 22.93 ms | 6.34 → 3.99 MB |

All six pairs improve at each size. The fixture has four entries per crate and a stored hash attribute on each regular file. Initialization is outside the timer. These are screening measurements; component processes do not have host-pressure capture.

Four balanced before/after phase pairs on the actual module show **145.17 → 143.49 ms before copying**. All observations are retained, including a slow baseline copy. The source and mirror walks run concurrently; the result is consistent with the faster engine walk being hidden behind the sender, receiver or diff work. It does not prove which of those remaining steps is dominant.

## Complete commands

Eight balanced randomized pairs per workload use the same physical sources and native history, with a fresh edit before every command. Native Cargo is a control. There is no forced collection or Go GC, and telemetry remains enabled through the local null receiver. These comparisons use the diagnostic switch in one binary, with the selected Rust module unchanged.

| Edited command | Default | Candidate | Cargo | Median paired saving | Faster pairs |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1,026-crate collection check | 1.393 s | 1.499 s | 0.776 s | −121 ms | 1/8 |
| 130-crate direct check | 0.639 s | 0.679 s | 0.129 s | −23 ms | 2/8 |
| Small collection tests | 0.942 s | 0.920 s | 0.503 s | +29 ms | 6/8 |
| 1,026-package listing | 2.856 s | 2.783 s | 0.437 s | +60 ms | 5/8 |

Column medians and the median of paired differences are different statistics. The listing Cargo control runs metadata discovery. These generated path-dependency workspaces do not establish registry, build-script or procedural-macro support.

The timing differences also include ordinary GC and host activity. Both check groups have Go GC in one baseline command and four candidate commands. Host I/O pressure reaches 12% during the wide checks, 29% during direct checks and 42% during small tests; listing pressure reaches 6%. Initial admission requires a quiet host, but pressure can rise afterward. Every admitted observation is kept. These data establish neither an isolated compiler regression nor a build speedup worth selecting.

A separate six-pair control preserves the original walker and directory-entry layout alongside the new default option. At 4,104 entries, the new default allocates about **87 kB more per walk**, with similar allocation counts and mixed timings. The extra option is therefore not free for unrelated default callers. Given the negligible elapsed import gain, adding that API and per-entry state is not justified here.

## Correctness and final state

The focused tests verify that the option preserves all returned metadata except the explicitly omitted attributes, including hardlinks and symlinks. Default scans and direct `Stat` keep attributes. Real snapshot imports produce identical digests for cold/warm imports, missing-hash repair, content edits and permission changes. The full affected `internal/fsutil` and `engine/filesync` suites pass, including the candidate race run.

All six native histories pass strict reuse with the candidate enabled: 130/130, 1,026/1,026 and 6/6 actions in each history. The preparation stage first compiles any final source edit left by the Cargo controls; these unchanged commands are correctness checks only. Initial test-harness compilation mistakes are retained alongside the corrected successful runs.

The original selected engine `f73ec4d9…` is restored through a clean preserved-volume restart. Parallel fingerprinting remains off, direct dimension-key getters remain on, and the Rust module remains `da1ae47`. No PR or additional upstream proposal is created.

The next investigation should follow the remaining critical work rather than speed up another overlapped walk: profile sender/receiver and diff operations before copying, and inspect the roughly 2.25 GB still allocated during complete package listings. The broader Rust-cache goal remains incomplete.

[Archived evidence](experiments/mirror-metadata/) includes completed spans and offsets, CPU/runtime/wcprof captures, exact source mirrors and hashes, candidate patch, all command samples and pressure, default-layout controls, tests, cache inspections and final engine state. Binaries, volumes and the original append-only telemetry receiver file are excluded. Absolute paths in the reproducible drivers need adapting on another checkout.
