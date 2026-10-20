# Configuration declaration reuse: current-main verification

This verifies the independent patch on Dagger main `ce6dc9f9403b52067f5831149eab4871f857185d`. The comparison copies the same added tests, benchmark and actual 1,649-byte Go configuration into an otherwise unchanged main checkout. Only the candidate changes production code. Both complete `core/workspace` race suites pass. The three production files involved in declaration loading are byte-for-byte unchanged since the older full-command comparison; hashes are in `config-review-source-continuity.json`.

Four alternating fresh-process pairs per scenario, 5,000 lookups per process, Go 1.26.6, GOMAXPROCS=8. The component benchmark runs without another heavy benchmark or build. These are component measurements, not a new complete-command result:

| Lookup | Main | Patch | Bytes allocated | Allocation count |
| --- | ---: | ---: | ---: | ---: |
| Repeated content | 324.928 µs | 3.989 µs | 130,719 → 48 | 2,818 → 3 |
| Concurrent repeated content | 139.608 µs | 1.178 µs | 130,725.5 → 50 | 2,818 → 3 |
| Distinct content | 335.409 µs | 351.0615 µs | 132,592.5 → 132,799 | 2,823 → 2,826 |

Repeated-content cases improve in all four pairs. Distinct inputs improve in one pair and regress in three; the median is 4.7% slower. Concurrent numbers are time per completed lookup across eight workers. The cache adds bounded retention, hashing, short LRU locking and miss bookkeeping. Parsing happens outside the lock. It has 32 entries, bypasses files over 64 KiB, and returns caller-owned slices. Warnings are delivered separately to each caller.

The [earlier full-command report](../../../../NATIVE_CONFIG_DECLARATION_REUSE.md) measured 45.51 → 40.65 seconds, 35.06 → 32.75 GB allocated and the same 4,398 rows. Those four alternating pairs used an experimental engine with all other changes fixed and only this decoder toggled. That is useful workload evidence, but it must not be described as a new whole-command measurement on current main. Its median paired saving is 4.21 s; the difference between the two version medians is 4.86 s. Do not add it to figures from other cohorts.

Tests exercise live edits and deletion, nearer configurations, read/parse errors, oversized files, caller mutation, concurrent reads and per-caller warnings. Tests pass on both implementations; they protect behavior rather than assert the presence of a cache.

`config-review-checks.json` retains exact commands and exit codes. Raw benchmark output, individual samples, summary, source continuity and the candidate patch accompany this report. An initial benchmark invocation used the wrong working directory and failed to find the fixture; it is retained locally in `config-review-harness-attempt01` and contributes no successful samples. The rerun uses the package working directory and preserves the prior race results.
