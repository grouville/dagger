# Telemetry queue experiment

See [the complete-command report](../../NATIVE_TELEMETRY_LINK_QUEUE.md). Component speedups are not full-command gains. No PR is opened.

The standalone patch changes OpenTelemetry's private FIFO implementation. The diagnostic setter, HTTP control and original/candidate wrapper exist only for paired experiments and are excluded from that patch. Each queue captures its mode when created, so changing the mode between complete commands does not reinterpret an existing span's storage.

Evidence includes source variants, meaningful FIFO/span/concurrency tests, original and candidate SDK checks, race results, all benchmark and listing attempts, exact source identities and restart/retention checks. Go files live under testdata. Large text captures use gzip; archive-manifest.json verifies compressed and original bytes. Drivers contain local absolute paths that need adapting elsewhere.

The SDK tree is an unmodified copy of go.opentelemetry.io/otel/sdk@v1.43.0, with version/checksums and a verified per-file inventory rather than another dependency source dump. Virtual modifications are archived. The binary is omitted with its SHA-256 and build command. No databases, native snapshot contents or Git metadata are included.

The profile context is derived from the already archived native-string-sort diagnostic, CPU windows at offsets 40.69 and 50.78 seconds. They overlap normal GC and include approximately one second after the command; cumulative CPU is not wall time. Their raw profiles remain in ../dang-native-string-sort/.
