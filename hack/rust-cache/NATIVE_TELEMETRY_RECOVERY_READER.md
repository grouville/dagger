# Return telemetry recovery readers to their pool

The one-line fix reduces allocation but remains **unselected for listing latency**. On complete Go test listing after a test edit, allocation falls **9.59 → 9.13 GB**, while elapsed time increases **8.45 → 8.68 seconds median**. Only one of four pairs is faster. Ordinary-source listing changes **5.51 → 5.54 seconds**, also faster in only one pair. This is not another measured speedup toward three seconds.

`spillFile.recover` borrows a 64 KiB reader from `frameReaderPool` but never returns it. Adding `defer scanner.release()` makes recovery follow the existing point-reader lifecycle. The defer also runs on corruption, cancellation and other errors. Recovery still decodes every record and invokes its callbacks; it neither discards telemetry nor defers command completion. `next()` allocates payloads independently of the pooled reader, so returning that reader does not invalidate recovered rows. The patch adds no lock or storage-format change.

Four alternating fresh-process benchmark pairs, Go 1.26.6 and GOMAXPROCS=8, include recovery but exclude file setup/open/close:

| Existing records | Time, before → after | Allocated bytes, before → after |
| --- | ---: | ---: |
| 0 | 8.21 → 0.11 µs | 65,732 → 72 |
| 1 | 8.97 → 1.05 µs | 65,788 → 128 |
| 512 | 58.11 → 52.36 µs | 86,263 → 20,607 |

All twelve component pairs improve. That does not override the complete-command results above. The standalone telemetry-store race suite passes, as does the diagnostic engine's full store race suite with native telemetry codecs and the candidate enabled. Existing tests exercise retained recovered rows, reopening indexes and streams, truncated writes, cancellation, failures and concurrent access. The patch adds a benchmark rather than a brittle `sync.Pool` identity assertion; the runtime may discard pool entries, particularly under the race detector.

The isolated engine compares only recovery-reader return. Indexed interface matching, the Go module, CLI and all other selected modes are common to both arms. Each workload completes test addition/removal in both modes before four balanced pairs. All 24 commands use real edits and a fresh CLI on a warm engine, include ordinary GC, telemetry, output, final flushing and successful cleanup, and return correct ordered rows. CPU after a test edit changes **40.51 → 40.21 CPU-s**; the lower allocation does not establish lower elapsed time. First use, retained-cache restart and Rust edited-build latency are unmeasured.

Eighteen Go checks pass, covering discovery, custom settings, ownership, source snapshots, rebinding, selected tests, binaries and generation. Twenty-eight Rust/native-cache cases pass with their expected outcomes, including current/restored names, selected success/failure, excluded invalid neighbors, repair and workspace APIs. Four native-cache queries each report two actions and two hits. Both test-edited wcprof captures retain 804 evaluations, 1,494 SDK requests, 800 getter executions and 799 unchanged discovery hits. Source-only captures retain three evaluations, 572 requests and cached getters/discovery. All four streams have zero dropped or open events.

The initial Rust attempt stopped at an omitted local query helper; that harness failure is retained separately, and the complete corrected cohort passes. The raw samples retain a copied `indexed_interface_matching` annotation that varies by arm; the executed drivers actually enable matching in both arms and vary only `spill-recovery-reader`. `sample-mode-note.json` documents this annotation error without rewriting raw measurements. Timing, CPU, allocation and output fields are unaffected.

The fix and benchmark are pushed to [the standalone fork branch](https://github.com/grouville/dagger/tree/experiment/telemetry-recovery-reader), based on `ff0b029a4d270a651b9a8c7286babc79089066e4`. No PR is open. [Review description](PR_TELEMETRY_RECOVERY_READER.md), [all attempts, measurements, source identities and lossless profiles](experiments/telemetry-recovery-reader/). The sixth engine and its cache are retained; the previous five binaries and volumes are unchanged. Sources and switches are restored, with no active client. A latency retest is required before selecting this for the performance stack.
