# Fewer schema-read allocations do not make the listing faster

The complete edited Go test listing takes **37.13 → 39.14 seconds** over eight fixed alternating pairs. Only two pairs are faster. Temporary schema-buffer reuse reduces median allocation **29.21 → 28.38 GB**, but does not establish a command-time gain. The candidate remains disabled and unselected. No upstream proposal or PR is added.

| Pair | Existing input reads | Reused temporary buffer |
| --- | ---: | ---: |
| 1, candidate first | 36.11 s | 37.94 s |
| 2, control first | 49.75 s | 38.23 s |
| 3, candidate first | 39.71 s | 40.05 s |
| 4, control first | 35.81 s | 37.83 s |
| 5, candidate first | 38.16 s | 37.90 s |
| 6, control first | 34.77 s | 48.18 s |
| 7, candidate first | 35.07 s | 41.61 s |
| 8, control first | 40.18 s | 51.70 s |

All eighteen commands succeed, including CLI exit, cleanup and an explicit final log flush. Each measured invocation returns the identical ordered 4,398 rows. The excluded initialization pair adds a real test, returns 4,399 rows and takes 41.97 → 35.71 seconds. Removing it restores the expected listing. Every arm starts a fresh CLI and receives a source comment edit on the same warm retained engine. Telemetry and ordinary GC remain enabled. No admitted observation is discarded or rerun.

Median engine CPU increases **183.97 → 191.55 CPU-seconds**. These observations do not establish why the candidate's elapsed times are worse. They are sufficient to leave it unselected. Column medians and the median paired difference are preserved separately in the evidence.

## Why this was worth testing

The preceding marker-prototype allocation profile attributes about 7.70 GB to reading and preparing decoded schemas. The existing decoded-schema cache reads each immutable file into a growing temporary byte slice before hashing its contents. Borrowing a fixed prefix buffer removes repeated growth while retaining current-byte reads, the SHA-256 key, the existing eight-entry cache, the 1 MiB retention threshold and the streaming fallback for larger schemas. Each caller still receives its own schema copy. The borrowed bytes return to `sync.Pool` only after decoding and copying finish; ordinary GC may discard the temporary buffers.

The 591,953-byte exported schema gives a real component improvement over four fixed alternating pairs: **1.95 → 1.69 ms**, faster in all four pairs, with allocation **1.91 MB → 0.52 MB per read**. That measurement includes reading, hashing, cache lookup and an independent schema copy. It justifies checking a complete command, not selecting the change by itself.

The earlier profile uses the marker prototype, while the timing uses the unchanged selected Go module. Their work is not interchangeable; multiplying a component saving by the earlier invocation count would overstate the expected benefit. The measured command allocation reduction is about 0.83 GB. This experiment extends the isolated decoded-schema-cache implementation and is not a standalone patch against main.

## Correctness and measurement boundary

The full Dang v2 race suite passes for the original reader, the plain pooled prototype, and both modes of the actual controlled engine source. Existing tests check independent schema copies, concurrent callers, changed contents and bounded cache retention. Added behavior tests check data returned with EOF, preservation of other read errors, inputs on both sides of the retention threshold and shorter changed inputs after large reads. They make no timing or buffer-allocation assertions.

One engine binary contains both paths behind a diagnostic switch. The module, CLI, source, telemetry and other selected settings are identical between arms. All 35 Go library and development checks pass with the candidate enabled, including collection behavior, module-layout edits, generation and builds. Sources, configuration, flags and profilers are restored after the comparison. All six native Rust histories reuse every action before engine replacement, on their first calls after replacement, and after the comparison: 130/130, 1,026/1,026 and 6/6, twice each.

The old engine takes 230.88 seconds to exit gracefully before this candidate is installed. Its recorded stacks show the cache persistence transaction inserting SQLite mirror rows. This is an observation about the previous engine and retained state, not candidate overhead or a matched shutdown comparison. No cache volume is reset and no engine is forcibly terminated. The new engine is identified by SHA-256 `67b5f92b5ec48ffeff12cf1a2c34d334cdd9d65f16087ecf54f5e2890ebf9060`.

A separate diagnostic of the unchanged selected module, with the buffer candidate disabled, returns the correct rows and exits in 43.94 seconds. Its 995,267 events have none dropped or open; all 7,820 SDK requests have exact admission and query links. A copied detail postprocessor initially retains the previous capture directory. Correcting that path completes the analysis of the original capture; no command is rerun. The original failure and correction remain archived.

The main query takes 40.04 seconds. Its critical path contains 10.06 seconds of field preparation, 5.14 around field invocation, 2.95 reading artifact dimension keys, 2.95 waiting for the session lifecycle lock, 2.62 publishing results, 2.49 in host directory calls and 2.32 in implementation-scoped module calls. These are separate path intervals, not predicted removable savings. The CPU sample attributes 3.98 cumulative CPU-seconds to Git-client declaration guards and 3.22 to finding installed implementation-scoped module candidates. Those stacks are a basis for the next targeted experiment; they are not elapsed command time and must not be added to the critical-path values. Schema reading contributes little on this path.

The [evidence archive](experiments/dang-schema-read-buffers/) retains the exact sources, useful tests, component pairs, every full-command observation, restart evidence and cache checks. The [transport screen](NATIVE_DANG_TRANSPORT_SCREEN.md) is separate and also selects no change.
