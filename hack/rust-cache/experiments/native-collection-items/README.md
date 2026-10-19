# Native stored-item collection prototype

[Results, tradeoff and remaining validation](../../NATIVE_COLLECTION_STORED_ITEMS.md), [review notes](../../PR_NATIVE_COLLECTION_STORED_ITEMS.md).

This prototype improves test-edited complete listing 10.81 → 7.04 seconds, while ordinary-source listing regresses 6.00 → 6.52 seconds. It is not selected as the default, not a ready upstream PR, and has no measured cold-start gain.

`module.patch` changes the Go module to provide keyed stored package entries. `engine-prototype.patch` implements the stored form of the existing get marker, including metadata projection, native lookup, content scope and Dang entry signatures. The engine patch is relative to the inherited experimental overlay stack, not standalone main. The archive preserves every replacement source and its mapping so that stack can be rebuilt.

`evidence.tar.gz` contains both module source archives, all 24 timing commands and outputs, eight focused module checks, core/SDK race and build records, capture drivers, counters, source/config restoration, the independent engine's activation/restart and final identities of all three engines. Initial core-test failures are retained in logs. The SDK source variant without entry signatures is retained; the report explains its observed registration failure. No profiler, build or check overlaps the complete-command timings.

`archive.json` identifies the verified archive; `manifest.json` hashes every member. Binaries and duplicate uncompressed wcprof streams are excluded. After unpacking, `python3 reconstruct.py capture-before` and `capture-candidate` rebuild the two lossless recordings; both were checked byte-for-byte. `analyze.py` preserves count/critical-path analysis and requires the diagnostic wcprof reporter. Drivers retain their original `/tmp` paths. The selected predecessor stack is documented in the [setup screens](../go-discovery-setup-screens/) and [improvement ledger](../../GO_COLLECTION_IMPROVEMENTS.md).

The original Go and Rust engines and their cache volumes remain unchanged. The new `dagger-collection-native-items-oct18` engine retains its independent cache for continued work. No PR is opened.
