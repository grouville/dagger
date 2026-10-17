# Fewer host requests do not yet make the listing faster

The combined stat/read experiment is **not selected**. Complete edited Go test listings take **44.67 → 51.24 seconds median**, with only one of four pairs faster. All ten commands, including initialization, return the correct ordered rows and exit successfully through cleanup. The [content-keyed declaration change](NATIVE_CONFIG_DECLARATION_REUSE.md) remains selected; this experiment adds no upstream proposal.

The earlier ten-second figure is cumulative CPU time in configuration parsing and validation, summed across concurrent calls. It is not file-open latency or ten seconds on the command's critical path. The [host trace](NATIVE_CONFIG_LOOKUP_COSTS.md) establishes 15,003 opens of the same unchanged 1,649-byte `dagger.toml`. Declaration sharing already reduces repeated decoding to one, while continuing to read current bytes.

## Two implementations

Reading first would avoid the stat for readable files. It doubles requests for missing files and directories, however, and can turn a metadata failure into success. A focused regression passes on the original helper and fails on this shortcut: readable contents incorrectly hide a `PermissionDenied` stat error. This is an injected metadata failure, not a claim that an ordinary Linux permission fixture reproduces that combination. The real combined-operation transport test preserves the same failure. The read-first variant is never installed in the engine.

The measured alternative performs the existing stat and read in one file-service stream. It preserves their order, metadata errors, directories, file and directory symlinks, broken links, size limits, cancellation and edits. The CLI sends the stat followed by the contents. An older CLI ends the stream after the stat, so the engine falls back to its existing separate read. Older engines keep using their separate requests. No generated protocol or cache-key format changes.

The regular-file component benchmark improves **223 → 202 µs**, with **54.7 → 35.0 KB** allocated per lookup and two requests becoming one. Missing paths slow **108 → 121 µs**, and directories **108 → 149 µs**, despite keeping one request. The added operation initializes network accounting before it knows whether a read will be needed. Telemetry is retained throughout.

Focused race checks pass for the actual engine utility client and CLI file service, including old-source compatibility. Existing CLI glob/search checks and the core no-tree behavior check also pass. Both binaries build successfully. The older CLI reuses all six native Rust histories on its first call after the candidate engine restart, exercising the compatibility path in a real engine.

## Complete commands

The command is `dagger check --module go --check test --list --all` on `dagger/dagger`, using the same local Go module, matched CLI and engine in both arms. Every arm starts a fresh CLI and edits a used source file on the retained engine. Telemetry and ordinary GC stay enabled. Declaration sharing, built-in receivers and sparse usage sampling are common; profiling and diagnostic counters are off during timing.

| Pair | Separate stat/read | Combined stream |
| --- | ---: | ---: |
| 1, candidate first | 40.18 s | 51.42 s |
| 2, control first | 43.17 s | 51.06 s |
| 3, candidate first | 49.97 s | 39.33 s |
| 4, control first | 46.16 s | 51.65 s |

Every measured command lists the same 4,398 rows. The excluded initialization pair adds a real test, lists 4,399 rows and takes 46.11 → 40.18 s; removing that test restores the expected listing. No admitted attempt is discarded. Median paired saving is **−6.69 s**. Median CLI CPU falls **28.35 → 24.74 CPU-seconds**, while engine CPU rises **219.16 → 231.29 CPU-seconds** and cumulative allocation **33.43 → 35.40 GB**.

Initialization records 42,050 file-service requests in the control and 27,047 in the candidate: **15,003 fewer requests**. These counters cover all file-service operations, including missing ancestor configurations. The candidate uses 26,804 combined requests, 217 ordinary stats and 26 ordinary reads. Reduced transport work is real; a complete-command benefit is not established.

## A cache-maintenance stall

A separate diagnostic completes in 55.30 s, with correct rows, successful cleanup and **570,363 wcprof events, zero dropped and none open**. Its main query attributes **25.86 s** to synchronous API intervals and **13.02 s** to publication. These include waits and must not be read as CPU costs or compared as a controlled latency difference with the previous capture.

Several publication spans stall between approximately **43.32 and 50.61 seconds**. The goroutine snapshot at 46.94 seconds finds **91 goroutines blocked entering result publication** and one running cache-index compaction. The source confirms that publication and compaction acquire the same cache lock. CPU windows aligned with that stall contain 6.07 CPU-seconds in compaction; the whole capture contains **7.45 CPU-seconds** and **1.46 GB of sampled cumulative allocation** beneath that function. These nested figures must not be added together.

This establishes a concrete maintenance bottleneck in the real collection path. It does not establish why the combined-operation cohort encounters more overhead, or what a compaction change would save. Ordinary collection remains enabled, every attempt is retained, and this candidate stays disabled.

Compaction rebuilds digest sets whose contents remain unchanged when class identifiers are renumbered. The next small experiment should audit ownership and test retaining those sets, then measure compaction and complete edited listings. Input slices and reverse indexes need separate aliasing and canonicalization checks; they should not be reused merely because they look similar. No compaction patch or speedup is claimed here.

A larger configuration improvement would share one explicitly versioned configuration input across dependent calls. Existing workspace read epochs are not a drop-in replacement: these reads follow the module's own host and nearest configuration, and declarations affect cache reuse and Git credential access. A change needs a clear freshness boundary and tests for edits, nearer files, failures and owner isolation.

The original selected engine is restored gracefully on the same volume. All six native Rust histories retain every expected action before and after the candidate restart, after the cohort and capture, and on their first call after restoration: 130/130, 1,026/1,026 and 6/6 on both sides. Profiling is off. The [archive](experiments/config-host-stat-read/) retains both rejected approaches, the useful tests, complete measurements, aligned profiles and source identities. No PR is opened.
