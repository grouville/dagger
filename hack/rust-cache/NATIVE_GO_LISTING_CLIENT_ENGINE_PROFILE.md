# Profile the CLI and engine together

The next diagnostic returns the expected **4,398 rows** and exits successfully. It records CPU and allocation samples in both the CLI and engine, plus complete engine wcprof events. Its **62.13-second** duration is diagnostic, not a new latency result. The last selected full-command comparison remains **53.58 → 46.72 seconds**. The [parallel-admission experiment](NATIVE_GO_LISTING_LOCKS.md) remains disabled after its full-command comparison failed to establish a useful improvement.

## Recorded costs

The CLI contributes 26.10 sampled CPU-seconds over 60.01 seconds of CPU windows. Its complete process uses 24.08 user and 4.76 system CPU-seconds. Significant stacks include filesystem synchronization (3.94 sampled CPU-seconds), frontend dispatch (3.43), telemetry consumption (2.83), and background marking (4.53). These cumulative stacks can overlap and must not be added as independent costs. This does not identify one dominant CLI bottleneck or justify disabling telemetry.

Engine windows cover 65.52 seconds, including roughly 3.4 seconds after command completion, and contain 257.22 sampled CPU-seconds. Allocation and collection remain substantial: the command allocates 41.28 GB cumulatively; background marking accounts for 54.66 sampled CPU-seconds and allocation assists for 19.20, on distinct stacks in this capture. Telemetry conversion and Dang callbacks also occupy substantial CPU and allocation stacks. Optimizing a small allocation source in isolation has repeatedly failed to improve full command time.

The main query, operation 5576, lasts 60.24 seconds. Its critical path attributes 34.27 seconds to synchronous Dang API requests, 11.17 to artifact element materialization, 5.64 to result publication and 5.48 to dimension-key element materialization. These are elapsed intervals on one path, not CPU totals. Indexed element labels inherit the containing resolver's name; they do not mean the list resolver ran again for each element.

## A concrete module loop to investigate

Rerooting wcprof at a long nested request, operation 29291, identifies `gomod:GomodGoMod.ownFiles`, used to discover a module's package files. That request lasts 8.18 seconds. Its function evaluation, operation 31128, makes **162 directly recorded API requests** totaling 5.054 seconds; evaluation outside those requests takes 1.83 seconds on this path. These counts are verified from the raw events, rather than inferred from overlapping timestamps.

`GoMod.nestedRoots` maps discovered roots through the module API's `gomod.workspaceRootPath`, whose implementation reads the workspace's working directory while converting each path. This suggests a small module experiment: read that immutable working-directory value once and calculate paths locally through shared code. Preserve relative paths, parent traversal, nearest-root selection and package/test granularity. The profile does not yet establish the full-command benefit of that change, or attribute every API request to path conversion.

## Capture boundaries

The command uses the selected CLI and Go module, a fresh CLI/source edit and a warm owned engine. Telemetry and ordinary GC remain enabled. Admission concurrency, parser reuse, lazy scope maps, resource batching, circular queues, callback reuse and flush coalescing remain off. CLI CPU capture uses its existing loopback `PPROF` listener, avoiding the `CPUPROFILE` option that also starts a Go runtime trace. No runtime trace or forced collection runs.

There are twelve complete CLI CPU windows, thirteen engine windows and thirteen CLI allocation snapshots. The CLI closes its last in-progress profiling request when it exits; that expected partial tail is retained as an error record, not treated as a listing failure or a complete CPU window. CLI allocation attribution compares the initial snapshot with the last available live snapshot and does not cover the final process tail. Heap allocation samples can lag live allocation by two GC cycles.

All 570,448 wcprof events are retained, with zero dropped or open operations. Host I/O stalls are 0.10%, engine I/O 0.006%; CPU pressure is 16.95% and 9.01%. No explicit CPU quota, memory limit, GOGC, GOMEMLIMIT or GOMAXPROCS setting is present on the owned container. A later idle snapshot reports 4.75 GB allocated heap and an estimated 3.99 GB of cache metadata; command peak heap must not be described as retained memory.

[The evidence archive](experiments/go-listing-client-engine-profile/) retains both processes' profiles and window boundaries, raw wcprof chunks, critical paths, row verification, source identities and restored settings. The [preceding cohort's allocation attribution](experiments/session-parallel-client-init/) is a separate window covering both admission modes and retained-history checks; its cumulative samples are not a per-command or per-arm benchmark. No new optimization is selected and no PR is opened.
