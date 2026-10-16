# Performance changes prepared for review

Six independent branches are pushed to [grouville/dagger](https://github.com/grouville/dagger), each based directly on main `717589c9cc`. No pull requests have been opened. Each description is ready for individual approval and includes the measurements, validation and tradeoffs.

| Proposal and description | Measured component, before → branch | Complexity and risk | Fork branch |
| --- | --- | --- | --- |
| [1. Skip scalar-array ownership walks](primitive-owners.md) | 1,024 strings: snapshot ownership **181.70 ms → 88.34 µs**; part-host attachment **181.11 ms → 239 ns** | A four-type switch; custom scalar resources and cleanup keep the generic path. Small cases also improve. | [Code](https://github.com/grouville/dagger/tree/perf/upstream-primitive-owners) |
| [2. Encode scalar arrays directly](primitive-encoding.md) | 1,024 strings: **181.46 ms → 531.18 µs**; allocated bytes **405.29 MiB → 272.40 KiB** | One specialized helper. Tests compare complete encodings with the generic path; stored format and errors remain compatible. Small cases also improve. | [Code](https://github.com/grouville/dagger/tree/perf/upstream-primitive-encoding) |
| [3. Allocate usage maps when populated](cache-usage-maps.md) | 200,000 cached results: **586.47 ms → 507.08 ms**, **600,000 fewer allocations** | Small change within the existing locks. Nil-map reads and stale ownership cleanup were reviewed; existing race tests cover the lifecycle. | [Code](https://github.com/grouville/dagger/tree/perf/upstream-cache-usage-maps) |
| [4. Buffer artifact list output](artifact-list-output.md) | 1,026 table rows: **10.43 ms → 1.45 ms**; **6,163 → 8 telemetry records** | Fixes reproduced output loss. One-row link/CLI output costs about 1 µs more and 4 KiB for the buffer. Flush errors are tested. | [Code](https://github.com/grouville/dagger/tree/fix/upstream-artifact-list-output) |
| [5. Index collection ancestors](collection-key-index.md) | 1,000 collection fields: **1.50 s → 3.75 ms**, including index construction | Largest algorithm change of this batch: a local path/dimension index. One field costs 184 extra bytes with similar timing; 10 fields already improve. | [Code](https://github.com/grouville/dagger/tree/perf/upstream-collection-key-index) |
| [6. Skip snapshot scans after metadata-only eviction](skip-empty-snapshot-gc.md) | Metadata prune with 1,000 retained snapshots: **4.004 ms → 25.30 µs**; **~32,124 → 31 allocations** | One production line reuses the existing deletion signal. Real reclamation and startup collection keep that existing path. | [Code](https://github.com/grouville/dagger/tree/perf/upstream-skip-empty-snapshot-gc) |

These are function benchmarks. Their gains cannot be added together or treated as seconds saved on a complete Rust build. The array cases have one input path per returned string. The collection index is rebuilt for every measured call; there is no persistent warm index. The usage-map case measures preparation for disk pruning, with fixture construction outside the timer.

The usage-map change also has a [retained-cache comparison](../REAL_CACHE_USAGE.md): 59,192 real engine results, two eight-pair series, 563 → 538 ms and 567 → 530 ms for size measurement and prune-state preparation together. All pairs allocate less, with identical result counts and accounted bytes. This remains an accounting measurement; complete Rust-command savings are not established.

The measured tradeoffs support submitting all six for review. The collection index needs the closest algorithm review because it replaces ancestor selection. The scalar-array changes need review of type eligibility, persisted compatibility and resource ownership. None introduces shared state or a new lock. Full end-to-end Rust measurements on these isolated heads remain separate work.

## Measurement and validation

The first five comparisons use six fresh-process A/B and B/A pairs, with the same test sources on both sides. The baseline restores only the production files to main. Go 1.26.6, linux/amd64, Intel Core i5-9300H, `GOMAXPROCS=8`; 150 ms per case, except the 200,000-result usage snapshot, measured once per process. Builds and race tests completed before measurements began. Maximum recorded host pressure was about 4.2% CPU, 1.7% I/O and 0.1% memory during samples.

The three dagql branches each pass the full `./dagql` race suite. The CLI and collection branches pass focused unit suites with the race detector; the exact commands are in their descriptions. New compatibility tests pass on both arms. The CLI burst test fails on main because rows are lost, and passes on the branch in all three formats. Closed-pipe tests pass on both arms.

The sixth proposal uses a separate six-pair comparison on real temporary snapshot stores, with initialization and fixture insertion outside the timer. It improves both the zero- and 1,000-snapshot cases in all pairs. Seventeen focused server tests pass normally and under the race detector; the new regression fails on main in both scheduled and explicit pruning. Its [raw evidence](../experiments/snapshot-gc/) records host pressure over complete processes, including fixture construction, and retains initial harness failures. It establishes no complete Rust-command saving.

[Exact branch and base revisions](branches.json) and [raw benchmark/test evidence](evidence/) are saved alongside the descriptions. Each candidate has `summary.json`, per-process metrics and host pressure in `runs.json`, the raw paired logs, test logs and production-file hashes. `evidence/SHA256SUMS` covers those files. Large binaries are excluded.

The archived benchmark driver regenerates baseline overlays with `git show`. Its configs record the measurement worktree paths; recreate those worktrees at the recorded revisions or adjust their paths before running it. Each description also gives a direct `go test` command.

This batch contains engine and CLI changes. Rust module/cache changes and experimental engine APIs are outside these proposals.
