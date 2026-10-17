# Restored search metadata: no complete-command improvement

Complete warm-engine Go listing measures **36.34 → 36.19 seconds**, faster in only two of four pairs. The median paired difference is a 26 ms regression. All ten commands return the expected ordered rows and exit successfully, including cleanup. The candidate remains disabled. See [the study](../../NATIVE_COLLECTION_RESTORED_METADATA.md).

Extract `evidence.tar.gz` to inspect files under `testdata/`, ignored by Go package discovery. `MANIFEST.json` records source paths, sizes and SHA-256 hashes; all 365 archive members were verified after compression. Reconstruct the omitted raw wcprof file from the archived compressed chunks and capture driver. Local paths require adaptation for replay.

The archive retains the rejected SDK attribution and actual module-facing schema, exact expression mocks, the cache-reopen regression and expected control failure, source overlays and their copied dependencies, race logs, full listing outputs and timing samples, profiles, retained native-cache histories, graceful restart observations and final disabled state. The prepared standalone overlay is unvalidated. No binary, cache volume, compiler target directory or credential is archived.

The diagnostic removes all 7,507 search-result publications while preserving scalar reads. This does not establish faster complete commands. No upstream proposal or PR is added; the primary Rust timing manifest is unchanged.
