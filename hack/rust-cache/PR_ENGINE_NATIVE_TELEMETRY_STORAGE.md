Title: engine: store telemetry payloads as Protobuf

The engine encodes telemetry fields as JSON when storing them, then decodes them before forwarding or inspecting them. Large collection listings repeat this work for thousands of spans. Store these fields with the generated Protobuf codecs instead, and teach their readers and indexes to accept both formats.

On `dagger/dagger`, the complete `dagger check --module go --check test --list --all` command gives:

| Reversed-order confirmation, eight pairs | JSON storage | Protobuf storage |
| --- | ---: | ---: |
| Command time, including cleanup | 38.10 s | 32.78 s |
| Cumulative engine allocation | 29.32 GB | 24.98 GB |
| Engine CPU | 194.93 CPU-s | 148.33 CPU-s |

These are column medians. All eight pairs improve, and every command returns the same 4,398 ordered rows and exits successfully. An earlier eight-pair cohort improves in six pairs; both cohorts and all observations remain in the [measurement report](https://github.com/grouville/dagger/blob/experiment/rust-native-cache/hack/rust-cache/NATIVE_TELEMETRY_STORAGE.md).

Each invocation starts a fresh CLI and makes a fresh source edit on the same warm engine. Telemetry, ordinary GC and cleanup remain enabled. The comparison toggles only the writer codec in one development engine; both arms include other performance changes. It does not establish a speedup over an otherwise unmodified main, cold-start performance, or production Cloud latency.

The storage format advances to v2. Readers accept existing JSON and new Protobuf fields, including mixed histories. A valid v1 file is recovered, then its header is synced before new records can be appended. That sync happens once per upgraded file; ordinary appends acquire no new sync or lock. Older engines reject v2 telemetry files, so downgrading the engine requires handling those files. Compiler-cache storage is separate. Migration latency has not been measured.

Coverage compares complete exported spans, logs and metrics, reopens mixed histories and rebuilds their call, check, test and archive indexes. It also checks malformed payloads, format/type mismatches and buffer ownership. The client-database and archive race suites and focused server and core inspection checks pass on main plus this patch. Removing either the header sync or native call-frame lookup makes its regression test fail. The affected binaries compile. External telemetry exports keep the same messages.

[Review branch](https://github.com/grouville/dagger/tree/perf/native-telemetry-storage), based on upstream `ff0b029a`. No PR is open.
