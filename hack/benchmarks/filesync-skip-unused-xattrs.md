# Skip unused local-import xattrs: diagnostic checkpoint

This branch is experimental instrumentation, not a production-ready stack.
The standalone implementation and regression tests are on
`perf/filesync-skip-unused-xattrs`. Neither branch changes the CAS prototype.

## Why

Local imports load extended attributes before discarding them during stat
normalization. The engine mirror walk also loads attributes the differ does
not use. Its authoritative content hash is read separately, under the change
cache guard. Opt those two walks out of unused reads without weakening change
detection, changing the protocol, or adding a persistent index.

Default `fsutil.NewFS` and public `Stat` still read xattrs. Missing mirror
hashes are still re-read and repaired. Client and engine work overlap; the
sum of avoided operation times is **not** a wall-clock saving.

## Method

- Pinned upstream main: `523f3fe37b0d03f8fd7ee1aaa77b2ca0f1978b59`.
- Control: `5c71fec98385a5a27a02277c973c3a2999088467`, main plus diagnostics.
- Candidate: the same diagnostics plus the xattr opt-out and regression tests.
- Ruff: `c2cd236b9cc5b2149c74247e179d6567ec74066f`, private fixture clone.
- Six alternating pairs. Each arm gets a fresh engine volume and CLI XDG state,
  then initial import, unchanged import, fresh one-file edit, and unchanged
  edited import. Engine images and host OS caches are already available.
- Unchanged default GC. No eviction-affected samples or timing outliers removed.
- Headline engine time is the native wcprof `session.serveQuery` interval union,
  including lazy materialization. CLI wall time includes provisioning/lifecycle.
- All 48 commands passed source/digest checks and native wcprof
  completeness/replay gates. Outside the timer, both first-pair edited results
  passed complete export/readback validation for 12,025 entries.

## Results

Milliseconds. Paired saving is median(control minus candidate), **not** the
difference between independently calculated medians. With n=6, nearest-rank
p95 equals max and is not a stable tail estimate.

| Flow | Engine control median | Engine candidate median | Paired engine saving | Paired CLI saving |
| --- | ---: | ---: | ---: | ---: |
| Fresh engine/cache import | 2246.514 | 2159.781 | 78.536 | 126.566 |
| Unchanged after initial | 415.563 | 370.563 | 1.780 | -25.089 |
| One-file edit | 1135.115 | 1090.703 | 46.684 | 48.949 |
| Unchanged after edit | 374.390 | 358.463 | 37.155 | 75.194 |

Initial unchanged results are inconclusive, including a CLI regression.
Engine maxima were 1977.155/2018.480 ms on that flow; default-GC eviction
events were retained. First-pair edit counters showed approximately 33 ms
of client and 98 ms of mirror xattr work removed, but that pair's sync phase
improved only about 13 ms and its whole command was essentially unchanged.
Overlapping work counters must not be added together as predicted savings.

Profiling-off confirmation is pending. These are filesync-only diagnostic
results, not Rust/Cargo end-to-end results or a complete-install benchmark.

## Regression tests and reproduction

Both packages passed three race-enabled runs through the repository Go runner:

```sh
dagger --x-release 00cb7d3a0e8d1eb6ec672aa504db14e52a9d1e21 \
  -m .dagger/modules/go api call --source=. --cgo env \
  with-mounted-temp --path=/tmp with-exec --insecure-root-capabilities \
  --args=go,test,-tags=privileged,-v,-race,-parallel=1,-count=3,-timeout=300s,-run=^Test,./internal/fsutil \
  stdout
```

Repeat separately with `./engine/filesync`. Tests cover default xattrs,
opt-out metadata parity, directories, filtering, symlinks, hardlink identity,
and guarded hash lookup/repair even when a hash disappears after the walk.

The exact machine-local harness and raw evidence are preserved under
`/tmp/dagger-filesync-scan.DTJq7eRa`:

- `build-r2/receipt.json`, `build-r4/receipt.json`: test commands and source hashes.
- `build-r3/receipt.json`, `build-r5/receipt.json`: control/candidate build pins.
- `filesync-pairs-r1/RESULTS.md` and `RESULTS.json`: every sample and acceptance gate.
- `runtime-r9` through `runtime-r20`: command receipts, native profiles, analyzer
  outputs, engine logs, source manifests, and export verification.
- `prepare_filesync_pairs.py`, `run_phase_pairs.py`, `summarize_phases.py`:
  guarded fresh-engine setup, alternating sequence, and phase analysis.

The scratch harness is not bundled in this branch; those paths identify the
retained local reproduction, not portable downloaded artifacts. Build receipts
pin pre-commit dirty-file hashes, so subsequent commits do not change what ran.
The control build overlapped an unrelated `dagger-engine.coldtest` lifecycle
change; its original failed inventory flag remains preserved. Only artifact
consumption allowed that named-container exception. Timed measurements ran
after the user confirmed that experiment was finished.
