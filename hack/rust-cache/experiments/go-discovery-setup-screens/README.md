# Go discovery setup screens and nested-selection fix

[Complete results and limits](../../NATIVE_GO_DISCOVERY_SETUP_SCREENS.md), [independent type fix](../../NATIVE_DANG_NESTED_SELECTION_ELEMENTS.md).

The verified archive contains all three module screens: 72 successful complete-command timings, 23 passing focused check commands, six separate lossless wcprof/CPU captures, source archives, minimal module patches, drivers, outputs, resource counters and restoration records. Initial failed attempts and the bracketed-module-path counterexample are retained. All three performance candidates remain unselected.

The `dang-nested-selection-elements` directory contains the standalone before/after source, regression test, failing pristine-upstream result, passing focused/full race checks, exact engine overlay and all its replacement sources, build records, graceful restart, captured shutdown stacks and final engine identities. The original Rust engine remains unchanged. No new PR is opened.

`archive.json` identifies `evidence.tar.gz`; `manifest.json` gives every member's size and SHA-256. Binaries and duplicate uncompressed wcprof streams are excluded. After unpacking, run `python3 common/reconstruct.py <study>/capture-before` or `capture-candidate` to recover the complete recordings. All six reconstructions were verified byte-for-byte before archiving. `common/analyze.py` preserves the analysis commands and requires the diagnostic wcprof reporter. Original absolute paths are kept in drivers and overlay mappings; the saved source mappings and preceding [discovery-screen stack](../go-discovery-screens/) identify the environment to recreate.

The third comparison uses the corrected interpreter in both arms. Do not compare its lower baseline against earlier cohorts as another optimization gain. Cold-start effects are not measured here.
