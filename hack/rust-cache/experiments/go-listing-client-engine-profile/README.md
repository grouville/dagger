# go-listing-client-engine-profile

One full listing with both CLI and engine CPU/allocation captures and complete engine wcprof. Profiled duration is not a latency benchmark; the expected incomplete CLI tail is retained. See [the report](../../NATIVE_GO_LISTING_CLIENT_ENGINE_PROFILE.md). No PR is opened.

The manifest verifies source and archived bytes. Large text captures use gzip. Raw Go source lives under testdata. Executables and merged recorder derivations are omitted with hashes; build inputs, profile windows and raw recorder chunks remain available. No database, snapshot contents or Git metadata are included. The pinned telemetry SDK/module copies are identified by ../otel-evicted-queue/. Drivers contain local paths requiring adaptation.
