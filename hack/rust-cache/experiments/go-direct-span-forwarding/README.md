# Direct span forwarding on the real Go listing

The converter remains disabled: 41.12 → 40.70 seconds median, faster in only two of four complete-command pairs. All ten invocations return the correct ordered rows and exit successfully. No speedup or CPU saving is established. See [the study](../../NATIVE_GO_DIRECT_SPAN_FORWARDING.md).

Extract `evidence.tar.gz` to inspect the captured files under `testdata/` (ignored by Go package discovery). `MANIFEST.json` records their original paths, sizes and SHA-256 hashes. Every member was verified after compression. The duplicate raw wcprof file is omitted; its complete compressed chunks and the reconstruction driver are retained.

The archive includes the exact paired driver and all attempts; compatibility overlays and existing differential tests; strict retained-cache checks in both modes before timing and with the candidate after timing/profiling; the selected engine/source identities; the completed CPU/wcprof capture and derived reports; and the class-table maintenance observations. The baseline engine source context is preserved in the earlier scalar-projection archive. Original local paths require adaptation for replay.

No engine binary, cache volume, compiler target directory or credential is archived. The engine is not replaced, the Rust timing manifest is unchanged, and no upstream PR is opened.
