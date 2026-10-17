# go-listing-lock-profile

Sampled mutex/block waits and wcprof from the original admission policy. This is diagnostic evidence, not a performance improvement. See [the report](../../NATIVE_GO_LISTING_LOCKS.md). No PR is opened.

The manifest verifies source and archived bytes. Large text captures use gzip. Raw Go source lives under testdata. Executables and merged recorder derivations are omitted with hashes; build inputs, profile windows and raw recorder chunks remain available. No database, snapshot contents or Git metadata are included. The pinned telemetry SDK/module copies are identified by ../otel-evicted-queue/. Drivers contain local paths requiring adaptation.
