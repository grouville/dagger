# Invocation phase profile

See [the report](../../NATIVE_DANG_API_REQUEST_PROFILE.md). This is diagnostic evidence, not a latency improvement. The original HTTP/GraphQL client and engine pipeline remain in use; the wrapper only records the caller's synchronous API processing. Every API operation is verified to be parented under function evaluation.

The archive retains source, attribution tests, SDK tests/race results, complete engine overlays, a successful 4,398-row command, raw wcprof chunks, CPU windows, derivation commands, restart/retention checks and restored state. The large merged wcprof file is omitted with its hash; concatenate raw events with the final string table to reconstruct it. The binary is omitted with its hash and build command. The unchanged pinned SDK source is identified by the inventory in ../otel-evicted-queue/; the shared modfile used for this build is archived there too.

The CPU capture covers 50.04 seconds and includes roughly 4.5 seconds after the 45.54-second command. Cumulative CPU includes concurrent work and is not wall time. The main critical-path report is rooted at operation 7068; the default report also includes other outermost roots. Host I/O pressure was elevated and the capture must not replace an unprofiled benchmark.

Raw Go files are under testdata. Large text captures use gzip; archive-manifest.json verifies both original and archived hashes/sizes. Drivers contain local paths that need adaptation. No database, snapshot contents or Git metadata are included. No PR is opened.
