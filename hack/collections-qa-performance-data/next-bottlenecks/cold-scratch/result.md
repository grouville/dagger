# Cold Go compiler scratch: reject default change on current evidence

September 25, 2026. Moving only the SDK Go compiler's temporary directory to a
Dagger temporary mount does **not** establish a useful cold or warm improvement
on greetings-api. Keep this prototype disabled. The experiment did identify a
measurement trap: bytes still dirty at CLI exit can look like eliminated disk
writes when they are merely deferred.

The real command remains `dagger check -l --all` in the complete greetings-api
configuration, with the same experimental Dang/TypeScript stack as the current
2.662 s warm result. Baseline is the retained512 Cloud batching engine; candidate
is rebuilt from clean `c12a34663b` plus the existing complete overlay and only the
Go GOTMPDIR temporary-mount overlay. `prepared.json` records sources and binary;
`cold-scratch-abba/provenance.json` records both images, CLI and source hashes.
Image preparation/linking happened before the exclusive measurement window.

Four sequential new-volume runs reverse the variant order in the second pair.
Each has a ready engine, unchanged host page cache, a fresh CLI including exit,
Cloud enabled and no remote result cache. Two warm repetitions follow each cold
sample, then only that experiment's engine stops. No build or other benchmark
runs concurrently. All 12 commands return the exact 14 expected rows. All 4
engine stop commands succeed; their volumes remain. No OOM event is recorded.
These are unprofiled timing runs. Existing wcprof evidence identified build and
materialization as targets; no new wcprof profile is claimed for this experiment.

| Order | Variant | Cold command | Host full I/O pressure | Device mean write await |
| --- | --- | ---: | ---: | ---: |
| 1 | Baseline512 | 42.540 s | 12.853 s | 59.1 ms |
| 2 | Scratch tmpfs | 42.913 s | 12.712 s | 113.4 ms |
| 3 | Scratch tmpfs | 26.127 s | 0.185 s | 2.3 ms |
| 4 | Baseline512 | 26.735 s | 0.208 s | 2.2 ms |

The slow pair differs by 373 ms against the candidate; the quiet pair differs by
608 ms in its favor. Two pairs do not establish a stable speedup. The disk
regime changes by about 16 s for **both** variants. The 4 warm samples per variant
give medians 2.625 s baseline and2.833 s scratch; this blocked sequence is not a
separate alternating warm performance study, but offers no warm improvement.

| Variant/sample | Engine writes during command | Device writes | Dirty pages at start | Dirty pages at exit |
| --- | ---: | ---: | ---: | ---: |
| Baseline slow | 1403.9 MiB | 1530.3 MiB | 2.1 MiB | 448.8 MiB |
| Scratch slow | 660.1 MiB | 783.6 MiB | 1.3 MiB | 1189.1 MiB |
| Scratch quiet | 1520.7 MiB | 1648.3 MiB | 1.0 MiB | 327.4 MiB |
| Baseline quiet | 1422.1 MiB | 1559.8 MiB | 1.6 MiB | 425.0 MiB |

The first scratch sample appears to write 744 MiB less in the engine cgroup.
But its dirty pages at exit are 740 MiB higher. Subsequent warm commands continue
writing 38.6 and66.8 MiB at device level as those pages drain. This is evidence of
deferred writeback, not a 50% write reduction. As a rough cross-check only,
device writes plus net dirty pages are 1977 / 1971 / 1975 / 1983 MiB in chronological
order. This is not rigorous per-command byte accounting: the counters cover the
host, dirties can be redirtied or discarded, and writeback can overlap. It is
sufficient to reject the tempting interpretation of the partial I/O counters.

The candidate actually uses tmpfs: sampled shmem peaks are 132.1 and141.3 MiB,
compared with 0 for baseline. Sampled total engine memory is 2582/2615 MiB for
the candidate and 2484/2692 MiB for baseline (these values are binary MiB in
raw data, not RSS). The host has ample memory, so zero OOM here does not validate
small CI memory limits. tmpfs competes with compiler anonymous memory and can
cause ENOSPC/OOM where disk-backed scratch would work. There is no measured gain
here to justify a broader SDK default or extra fallback complexity.

This reinforces prioritizing elimination of unnecessary compilation and demanded
filesystem materialization, and checking existing SDK entrypoint work first.
The remote cache can avoid compatible builds, but demanded layers still need
local materialization. The ordinary Go seed cache already uses a COW snapshot;
there is no full seed-directory copy to remove.

Raw evidence: `cold-scratch-abba/summary.json`, per-run `result.json`,
`summary.json`, `samples.json` and stdout, plus `abba.log`. No source change or
upstream commit was made from this experiment.
