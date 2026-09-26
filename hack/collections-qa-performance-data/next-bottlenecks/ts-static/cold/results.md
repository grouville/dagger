# TypeScript static-schema cold experiment

The low-I/O-stall pair improved from **26.65 s to 25.45 s** (1.20 s, 4.5%). A slower pair improved from 46.04 s to 36.13 s, but its unequal I/O stalls prevent attributing that entire difference to the prototype. These are two observations, not a stable general cold-start percentage.

## Scope

Both variants run the normal `dagger check -l --all` command in Kyle’s greetings-api fixture, using a fresh Dagger volume for every cold sample. Timing covers the complete new CLI process through exit after the engine is ready. Image preparation, binary/blob copies, and engine startup are outside the CLI timer; startup-to-ready is recorded separately. Host page cache remains intact. Direct Cloud telemetry stays enabled, and distributed cache is disabled.

The control already includes the combined Dang/prebuilt TypeScript/direct Node/Node compile-cache improvements. The candidate adds the pinned TypeScript static-schema prototype; it is not a released general-purpose SDK. This comparison measures that increment, not the full improvement over upstream collections.

## Results

| Run | Variant | Cold CLI (s) | Immediate warm (s) | Engine I/O full stall (s) | Host I/O full stall (s) | Classification |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| 0 | control | 30.297 | 2.644 | 0.862 | 6.301 | Potentially contaminated |
| 1 | static | 29.354 | 3.931 | 1.826 | 3.305 | Context |
| 2 | static | 36.133 | 2.855 | 5.613 | 9.095 | Primary BAAB |
| 3 | control | 46.045 | 3.119 | 14.108 | 14.680 | Primary BAAB |
| 4 | control | 26.647 | 2.798 | 0.082 | 0.198 | Primary BAAB |
| 5 | static | 25.447 | 2.129 | 0.055 | 0.084 | Primary BAAB |

Run 0 overlapped an accidental broad read-only filesystem walk by another agent for approximately 10–15 s. Exact timestamps are unavailable. All original data is retained; two additional fresh-volume measurements supplied a clean **static/control/control/static** sequence (runs 2–5). No compilation or other benchmark overlapped those primary samples.

The low-stall pair has engine I/O-full pressure of 0.082 s versus 0.055 s. The slow pair has 14.108 s versus 5.613 s. The same control binary varies from 26.65 s to 46.04 s while its I/O stalls increase from 0.082 s to 14.108 s. That is concrete evidence of a substantial storage contribution to the variability. PSI full-stall time can overlap other work and is not a stopwatch decomposition of command latency.

All **12/12 invocations** exited successfully and produced the exact expected listing, SHA-256 `c5ab5a8e1e456367b3c15e934d3d6fd7d62b315967d8d7c9571a24b2bbde63d6`. The one warm follow-up per cold volume is context, not a dedicated warm comparison. All six task-owned engines were stopped; volumes and raw data are retained.

## Disk accounting

| Run | Engine writes during cold (MiB) | Dirty start → end (MiB, host) | Device writes during cold (MiB, host) | Device mean write await (ms) | Peak engine memory (MiB) |
| --- | ---: | ---: | ---: | ---: | ---: |
| 0 | 1101.5 | 2.0 → 767.4 | 1188.6 | 22.61 | 2512.3 |
| 1 | 603.6 | 2.8 → 1000.5 | 673.1 | 33.23 | 2242.6 |
| 2 | 1108.0 | 2.3 → 461.7 | 1226.2 | 64.15 | 2260.8 |
| 3 | 1316.4 | 3.2 → 546.5 | 1419.3 | 79.33 | 2686.1 |
| 4 | 1730.0 | 2.0 → 204.6 | 1829.2 | 3.05 | 2541.9 |
| 5 | 685.7 | 2.1 → 917.7 | 745.6 | 1.38 | 2256.4 |

Cold-window write counts alone exaggerate avoided work. Run 5 writes 685.7 MiB during cold but leaves 917.7 MiB of host dirty pages; its immediate warm command then writes another 768.1 MiB while dirty pages fall. This is delayed writeback, not evidence that the warm listing generated that much new data. Host device writes plus the change in host dirty pages are a rough accounting cross-check, not exact per-command or per-process physical writes.

The high-stall runs had more than 51 GiB of host memory available. Most sampled cgroup writes belonged to the active engine, with only small journald/other-scope activity. This does not establish a particular NVMe hardware cause or justify treating all wall-time variation as local Dagger work.

## Interpretation and next step

Static metadata removes executable schema-loading work and helps even without remote cache. Distributed cache may avoid recomputation when there is a matching entry, but transferred snapshots and local materialization still incur I/O; it does not guarantee elimination of the disk stalls observed here. The next upstream design should generate and validate metadata through the SDK/cache identity rather than hard-code this fixture. The existing Go tmpfs experiment did not demonstrate a consistent gain, so it remains disabled.

## Reproduction and provenance

- Driver: `cold_abba.py`; preparation and benchmark are separate actions.
- Original four runs: `cold-ts-static-abba/{prepared.json,summary.json}`.
- Replacement fresh pair: `cold-ts-static-extra-ab/{prepared.json,summary.json}`.
- Machine summary: `results.json`; each raw command directory retains result, samples, stdout, and stderr.
- Control binary SHA-256: `b4955e7056c1e646077a2e6a8a74d77e8a6763a31e921feeb792ce5d8274dcac`.
- Static candidate SHA-256: `a1b41acdd93b65fd0a3baf3078f70ef51ab1293a0c5526f473e60c57cc875cf5`.
- Workspace: `/tmp/collections-perf/sdk-edit-audit/ts-static/greetings`.
- CLI: `/tmp/collections-perf/rebase-main/dagger`; its hash and fixture hashes are in both `prepared.json` files.
- Base image: `localhost/dagger-engine.collections-perf:latest`, pinned by image ID in `prepared.json`.
- SDK manifest: `sha256:2a8f755cfe5322aeeee861f646c58d6b796a585d2794db47b5b71ba14f6f3fef`.
- No relay was used in this cold comparison.
