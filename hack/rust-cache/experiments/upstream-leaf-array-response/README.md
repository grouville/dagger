# Upstream scalar-list adoption: no full-command gain

The latest selected Go listing takes 40.28 seconds; broader upstream scalar-list rendering takes 40.72 seconds and loses three of four pairs. All commands return the correct ordered rows and exit successfully. The candidate remains disabled. See [the study](../../NATIVE_COLLECTION_UPSTREAM_LEAVES.md).

Extract evidence.tar.gz to inspect files under testdata/, ignored by Go package discovery. MANIFEST.json records original paths, sizes and SHA-256 hashes. Every archive member was verified after compression. Reconstruct the omitted raw wcprof file from the compressed chunks and archived capture driver. Local paths require adaptation for replay.

The archive includes every component attempt, corrected benchmark builds and identities, full command outputs, exact engine/test overlays and their source, upstream provenance, race checks, retained Rust-cache verification, graceful restart captures, complete wcprof/CPU captures and the final disabled state. No engine binary, cache volume, compiler target directory or credential is included.

This adopts already-upstream work for an older retained diagnostic. It adds no upstream proposal or PR, and changes no Rust timing claim. FOLLOW_UP.md records a separate, unimplemented native search-result candidate.
