# Dang in-place cloning: local command comparison

All 36 expected outcomes passed, including exact 14-row check listings, ordered artifact parity, real selected Go-test execution, deliberate test failure and recovery, and exact native generated output. The four-block ABBA comparison does **not establish a broad command-time improvement**. Keep the source optimization separate from any claimed user-visible speedup.

Both engines use the same retained effective 6a82 stack, frozen SDKs, ordinary image init, original CLI, local Go module with `baseAddress`, and shared retained volume. Only the Dang syntax-cloning implementation differs. Both engines also include identical fixed-label telemetry-flush profiling; neither changes flush behavior. This is not current-production versus the entire experimental stack.

## Ordinary observations

Times below are milliseconds, in chronological order within each arm. There are only two observations per arm and flow. ABBA blocks restart the engine and explicitly prime the two listing commands; shared persistent state and block order make these correlated observations.

| Flow | Baseline raw | Candidate raw | Baseline median | Candidate median |
|---|---:|---:|---:|---:|
| Warm `check -l --all` | 1129.4, 1120.1 | 1144.8, 1128.9 | 1124.7 | 1136.8 |
| Warm `list -a` | 1103.8, 1226.3 | 1128.5, 1149.0 | 1165.0 | 1138.8 |
| First-seen comment → check listing | 1618.9, 1134.6 | 1135.2, 1182.4 | 1376.8 | 1158.8 |
| Fresh input → native generation, full exit | 397.8, 346.9 | 353.9, 354.8 | 372.4 | 354.3 |
| Fresh input → native generated file visible | 374.2, 323.9 | 328.6, 327.9 | 349.1 | 328.3 |

Warm check aligned block differences are +15.4 and +8.8 ms. Artifact differences change sign: +24.7 and −77.3 ms. The apparent comment-listing improvement is dominated by the first baseline observation: aligned differences are −483.7 and +47.8 ms. These samples do not establish an edit-loop improvement.

Generation is an authored native Changeset generator, not SDK code generation. Its four first-seen input values were distinct, and each output was absent before the call. File visibility is sampled every 5 ms and is separate from blocking-wait CLI exit. These are correctness and first-demand controls, with no dedicated generation warmup after each engine restart; they are not a stable warm-generation benchmark.

## Actual check and first-demand cost

The first real selected Go unit check took **44.087 s** wall time. Default-progress output reports 43.2 s for that selected check and exactly one passing test. The saved output contains no internal compilation, download, service, or process phase timings, so this capture cannot assign the 44 s to a specific build.

Subsequent execution controls took 1.339, 1.275 and 1.362 s. The first baseline and candidate control do not have comparable first-use state. Do not report their difference or their medians as a cloning gain.

Each arm also ran a unique `t.Fatal` sentinel that had to fail the selected `TestFormatResponse`, then restored source and required exactly one passing test with no skips. Both failure and recovery gates passed. This gate exercises a real Go unit check; it is not the separate strict HTTP/E2E fixture.

## Profiles, resource boundaries, and limitations

Two additional fully primed diagnostic listings were captured after ordinary observations. Their instrumentation times are excluded from the table. The SDK audit separately reduces clone and telemetry-flush phases from these private profiles. A fixed-label metric phase with zero active readers is a valid result; the existence of all-client fanout in source does not prove it is costly in this run.

Every CLI used a fresh client/session with Cloud disabled and normal progress. Engines were new temporary containers on the same owned retained volume, with provisioning, start/stop, ownership checks and cgroup snapshots outside command timing. The captured engine CPU is cumulative across cores, not wall time. The 8 GiB write guard sums command-bracketed engine writes; startup, teardown and inter-command writes are outside that count. Host PSI and both process-tree and engine CPU counters are retained in numeric evidence, not used to infer a causal explanation for outliers.

There is no fresh-volume cold, service-up, remote-engine, production Cloud, or broad 500 ms claim. The fixture resides under the existing wide `/tmp` hierarchy, and this comparison holds that path constant.

All six lifecycle cleanups removed only their temporary container, preserved the retained volume, left the original engine stopped, and verified its engine/init binaries unchanged. App source/config/lock, native input/generated/lock, and the original public fixture were restored exactly. No further calls or retries were added.

`numeric.json` contains all 36 sanitized rows, raw group values, aligned block differences, source/build hashes, and restoration facts. Raw profiles, command output, container IDs, connection URLs and credentials are excluded from the public allowlist.

## Telemetry attribution: metric fanout is real, but small here

Both separate diagnostic listings captured 15 Dang completion barriers. Those barriers invoked actual per-client metric-provider `ForceFlush` 109 times in the baseline and 112 in the candidate. The provider marker starts after the provider mutex and non-nil check, so these are real provider invocations, not merely a snapshot of client records.

| Recorded phase, union milliseconds | Baseline | Candidate |
|---|---:|---:|
| Whole Dang completion barrier | 47.53 | 44.09 |
| All-session trace-provider flush | 37.61 | 37.36 |
| All-session log-provider flush | 7.29 | 4.83 |
| Aggregate metric flush, including scheduling/wait | 2.49 | 3.22 |

These phases can overlap across calls; neither their sum nor a phase's union is a guaranteed command-time saving. Nevertheless, they reject the proposed attribution of roughly49 ms to all-client metrics: that part is only about2.5–3.2 ms in this workload. The trace/log-only barrier prototype passed focused unit/race gates, but it also changes incidental gauge sampling and has no runtime performance trial. It remains isolated and low priority on this evidence. The trace flush dominates the measured barrier; no safe further reduction is established here.

The clone run itself does not isolate AST-copy time: `dang.runSource` contains parsing/cloning, inference, declaration and evaluation, while `dang.cloneSchema` describes a different decoded-schema copy. Do not substitute either as a direct measurement of the changed clone routine.
