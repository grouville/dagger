# Fresh-volume Go base Address comparison

Four first listings passed the same ordered 14-check output. Each ran on its own new Dagger volume, with no preceding Dagger call. Both arms used the same engine `38711bd2`, CLI `d6858098`, ordinary init, packaged SDK stack and workspace-relative Go module layout. The difference is original Go/base versus the explicit optional baseAddress module/config. No Cloud calls were sent.

| Order | Module input | Full CLI exit | Engine CPU | CLI-bracket writes | Host I/O full pressure |
| --- | --- | ---: | ---: | ---: | ---: |
| 1 | control | 25.533 s | 87.746 CPU-s | 1.361 GB | 0.182 s |
| 2 | candidate | 21.142 s | 87.523 CPU-s | 1.348 GB | 0.115 s |
| 3 | candidate | 20.918 s | 86.937 CPU-s | 0.708 GB | 0.139 s |
| 4 | control | 29.421 s | 88.563 CPU-s | 1.152 GB | 2.994 s |

The two candidate observations are 20.918–21.142 s; control is 25.533–29.421 s. Their descriptive midpoints are 21.030 s and 27.477 s, respectively (23.5% lower), but two samples per arm in one ABBA block do not establish a stable general gain. Host image layers, SDK blobs, host page cache and external registry/Git caches were retained. All fetches and compilation triggered by the first command stayed inside its wall interval; preparatory copies and engine readiness were outside.

Engine CPU remained 86.94–88.56 CPU-s across all four calls. These observations therefore do not demonstrate elimination of cold compilation. The last control also coincided with 2.99 s of host full I/O pressure, versus 0.12–0.18 s in the other three. That is evidence of a different storage environment, not proof that this explains its entire wall-time difference.

Write counts are sampled cgroup bytes around the CLI, not total materialization bytes. For example, the second candidate had only 0.708 GB of measured writes but ended with about 924 MiB of host Dirty pages (versus 7.3 MiB initially); kernel writeback timing can move writes beyond the CLI interval. These host-wide counters are not specific to Dagger. Pre-stop lifetime counters total 4.578 GB; final stop writeback and provisioning are excluded. No write/free-space/timeout guard fired.

Provisioning took 0.638–0.769 s per container, and engine start through debug readiness took 0.243–0.252 s; both were excluded and recorded. Stopping each dedicated engine took 13.21–26.36 s and was also excluded: the normal CLI command connects to an already running engine, and each subsequent cold sample used a different empty volume.

The original fixture remained untouched and the working copy was restored. All four new containers were removed. The four new volumes were initially retained as specified by the reviewed cleanup policy; the separate ownership-checked cleanup then removed all four. It completed in approximately 4.72 s according to filesystem timestamps (not a monotonic process timer), outside the CLI samples. No pre-existing engine or volume was referenced or modified.

This comparison is scoped to listings. The preceding nine-call correctness proof covered actual custom-base/service execution, source-edit failures and recovery. Additional GoDev QA is tracked separately; these numbers do not override a failing correctness gate. A separately budgeted first-call profile is needed to attribute the remaining cold work.
