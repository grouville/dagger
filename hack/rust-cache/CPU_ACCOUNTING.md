# CPU counters in the performance experiments

The benchmark drivers read the cgroup containing the engine's initial process. On the measured dev engine, that group is the Docker container's `/engine` child. Module helpers and compiler workloads run under its sibling `/exec` group.

| Measurement | Included work |
| --- | --- |
| Existing `engine_cpu_seconds` | Processes in `/engine`, including engine work that can continue after a session |
| Engine pprof | Sampled CPU of the engine Go process |
| Helper pprof | Sampled CPU of the separate helper Go process during the recorded interval |
| Docker parent cgroup | `/engine`, `/exec` and the container's other descendants |

The older metadata phrase “engine container cgroup usage_usec including descendants” was imprecise: those records do not include sibling helper or Rust compiler processes. The recorded values remain engine-only CPU measurements. They cannot establish total Dagger CPU, and compiler CPU cannot be recovered by subtracting them from elapsed time.

Complete command wall times, before/after pair membership and source edits are unchanged. The drivers also record host pressure; their separate engine pressure measurements use the same narrower `/engine` group. An idle-session check and the host pressure threshold still apply before timed launches.

The deep-chain diagnostic driver records `/engine`, `/exec` and the Docker parent separately. These are overlapping scopes: the parent total must not be added to its children. CPU profiles and these instrumented commands remain separate from the unprofiled latency comparisons.

The observed process paths and new measurements are archived with the deep-chain experiment. Earlier raw datasets and their hashes remain intact; this note corrects their interpretation.
