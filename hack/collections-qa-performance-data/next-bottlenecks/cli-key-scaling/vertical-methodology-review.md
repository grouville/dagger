# Five-flow timing review

The current fixture uses ordinary Workspace inputs and real public commands:
selected check, generation, HTTP service startup, explicit module call, and
host-file export. Warm runs avoid rewriting identical input bytes; edit runs
write fresh per-variant markers. Check failure/restoration proves the marker
is consumed, generated/exported files are checked byte-for-byte, module results
are exact, and each service run must serve the current bytes and release its
tunnel after intentional cancellation.

These are a tiny local synthetic Dang fixture and a retained experimental
engine. They do not establish the same result for Kyle's multi-module project,
Go/TS compilation, a fresh engine volume, or normal Cloud-enabled CLI exit.
Local-only describes telemetry/exporter configuration; BusyBox registry access
can still occur. Baseline and candidate should share the fixture image/tag.

| Observation | Meaning and limit |
| --- | --- |
| CLI wall | Fresh process start through exit observation in a blocking waitpid thread, including observer scheduling. |
| File visibility | Expected bytes became readable; 5 ms polling adds delay, and this is not fsync durability. |
| HTTP readiness | The configured port served exact current bytes; includes request time and up to 100 ms failed-request timeout plus polling. |
| Cancel to exit | Intentional service SIGINT through observed CLI termination; separate from readiness. |
| Check producer | The projected Void @check call constructs Check; it does not itself execute the authored verification. |
| Check.sync | Engine begins evaluating the selected check. |
| dang.invoke under Check.sync | Interpreter callback starts inside evaluation, including dispatch; not the first authored source instruction. |
| exec.processRun | A real subprocess runs, when the fixture actually requires one. Dang verification/module reads do not require a container process. |

The earlier timeout-based `Popen.wait(timeout)` has a polling reporting tail
that can approach 50 ms. Preserve v2 as preflight/diagnostic evidence; do not
combine its quantized wall samples with v3's blocking-wait samples.

The file observer can miss a fast write when the child exits between a failed
read and the next completion check. Final byte validation still proves correct
output, but visibility stays null. Report the number of observed visibility
samples and do not silently compare medians with different missing-sample
patterns. Warm generation with already-current output is correctly a no-op
visibility case, not a claimed instantaneous write.

The updated phase analyzer includes call/cache outcomes, session phases,
Container.from, network setup, interpreter ancestry and process execution.
It decodes argv only for exec.processRun, and records operations outside CLI
clock bounds instead of silently treating them as CLI overhead. Diagnostics
assert no dropped events/open operations. Intervals are nested and some calls
span cross-client work: neither summing them nor the wcprof self-time table
alone proves CPU consumption or a removable wall-time saving.

One shared workspace intentionally carries previous generated/exported files
between flows. That resembles an evolving project, but it is not a set of
independent per-command cold environments. Unique edit bytes also do not imply
all downstream caches are cold. Preserve the command order and fixture hashes.
Source/config and input freshness are covered; process/cache outcomes determine
whether a successful warm check actually ran its function again.
