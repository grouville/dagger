# Where the CLI spends CPU during the full Go listing

The selected CLI consumes roughly 26 CPU-seconds per complete listing even after native engine telemetry storage lowers engine work. A capture using the **unchanged CLI binary** locates that work across host filesync, directory traversal, telemetry/UI processing and garbage collection. It does not identify a single 20-second parser or establish another speedup.

## Capture and limits

The command is `dagger check --module go --check test --list --all` on source `ff0b029a`, with Go module `7568cd0`, CLI `e7ba08d0` and engine `4080ad95`. The engine is warm, the CLI process is fresh, and a fresh source-comment edit is applied. Native telemetry writing is enabled only during capture, after the two timing cohorts have finished. Telemetry, normal Go GC, ordinary cleanup and the final engine-log flush remain enabled.

The existing `CPUPROFILE` support also captures a Go runtime trace. No instrumentation patch or CLI rebuild is needed. This adds diagnostic overhead; the capture is excluded from all timing medians. The CPU profiler starts in the CLI's persistent pre-run hook and stops through Cobra finalization, so it is not an exact account of every process instruction.

The complete command succeeds in **34.74 seconds**, returning the exact **4,398 ordered rows**. Process accounting reports **22.37 user + 4.63 system CPU-seconds**, with **670,816 KiB maximum RSS**. The profile contains **24.90 sampled CPU-seconds over 33.84 seconds**. The original profile and a losslessly compressed **36.72 MB runtime trace** are retained.

## Findings

| Profile frame | Cumulative sampled CPU |
| --- | ---: |
| Filesync request handler | 4.53 s |
| Directory walking across all callers | 2.50 s |
| Pretty frontend dispatch | 2.99 s |
| Frontend span-export path | 2.21 s |
| Telemetry-response consumption | 2.18 s |
| Go background marking | 3.05 s |

These frames overlap. Directory walking is nested beneath some filesync handlers, frontend span processing appears in several telemetry paths, and runtime work serves all callers. The column must not be summed or interpreted as removable elapsed time. Flat samples also include **3.04 seconds in Linux syscalls**; that is not an additional independent cost.

The selected host-glob function accounts for **1.48 cumulative CPU-seconds**. Its callback attributes **0.67 seconds** to matching paths and **0.11 seconds** to deriving relative paths. The broader 2.50-second walking frame therefore is not all glob matching. Path expansion/normalization accounts for only **0.05 seconds**, making it a poor first target.

Within filesync handling, incoming trace-context extraction accounts for **0.84 seconds**, import-option decoding for **1.08 seconds**, actual stat calls for **0.28 seconds**, and file reads for **0.40 seconds** in this sample. These are sampled CPU costs, not RPC latency. The [engine's separate critical-path capture](NATIVE_TELEMETRY_STORAGE.md) still attributes 9.33 elapsed seconds on its main-query path to fresh configuration stats and reads. Reducing protocol/setup work within one fresh lookup is a different experiment from caching a previously read configuration.

## Choosing the next change

The data supports investigating fewer host round trips for one logical lookup, traversal/matching work, and CLI telemetry processing. Each needs a concrete hypothesis and complete-command validation. The [earlier combined stat/read experiment](NATIVE_CONFIG_HOST_REQUESTS.md) already reduced requests without proving a latency gain; repeating it unchanged is insufficient.

Configuration freshness and metadata errors stay part of the contract. The previous in-progress-sharing prototype fails a regression when an edit completes before a later caller starts, so it remains rejected. A future batched lookup must retain a fresh read for each module call, nearest-file behavior, the correct source owner, metadata failures, cancellation, size limits and older-client compatibility. This profile does not establish that a new batching design meets those conditions.

No telemetry suppression, shared mutable filesystem cache, CLI optimization or new library is selected by this capture. The confirmed native-storage result remains a separate engine change, pending standalone extraction and migration review.

## Source and final state

Line-level reports use a source mirror matching the CLI's build overlay, including its selected literal-prefix glob optimization and buffered list writer. Reading the checkout's unmodified source at the profile's recorded absolute filename would otherwise show the wrong lines. The source map and hashes are archived; the raw profile is unchanged.

Sources, workspace configuration and feature flags are restored. All six retained native Rust histories still hit every expected action after the capture: **130/130, 1,026/1,026 and 6/6**, twice each. The final engine is idle, profiling is off and native writing is disabled. Dual-format readers and outer-store v2 support remain installed; restoring a v1-only reader over those telemetry files is not a rollback procedure.

[Evidence](experiments/go-listing-cli-cpu/) includes the capture driver, exact binary/source identities, all command outputs, full CPU profile, compressed runtime trace with verified hashes, corrected source reports and final restoration checks. No PR is opened.
