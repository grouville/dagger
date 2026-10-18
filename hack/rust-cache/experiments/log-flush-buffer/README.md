# Log flush-buffer experiment

See [the assessment](../../NATIVE_LOG_FLUSH_BUFFER.md). The component result saves most of the flush allocation, but eight full-listing pairs measure 34.38 → 35.36 seconds with only 3/8 faster. All pairs allocate less. The option remains off and no PR is proposed.

The archive retains the SDK source variants, incompatible upgrade attempt, race checks and expected-failure control, component samples, all eighteen complete commands, warm-up counters, engine source mapping, graceful restart, all three sets of Rust cache checks and restoration. The plain patch is provided for review and targets the legacy SDK; it is not an upstream-main proposal.

MANIFEST.json records every member and archive hash. Original absolute paths need adapting for replay. Existing engine dependency context is in the earlier [native telemetry archive](../telemetry-native-storage/); the current SDK sources and all selected engine overlays are included here. No engine binary, cache volume or credentials are included.
