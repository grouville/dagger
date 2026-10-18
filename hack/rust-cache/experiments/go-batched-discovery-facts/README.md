# Batched Go discovery facts

See [the assessment](../../NATIVE_GO_BATCHED_DISCOVERY_FACTS.md) and [prepared PR description](../../PR_GO_BATCHED_DISCOVERY_FACTS.md). Complete edited listing improves 25.45 → 19.21 seconds median in four alternating pairs, with identical rows and successful cleanup. This is a warm development-engine comparison, not stock main. Three seconds remains unachieved.

The archive retains the exact three-file module patch and source snapshots, source identities, all ten commands (including initialization), 27 passing checks and earlier harness failures. Separate lossless wcprof captures establish 7,820 → 4,845 nested SDK requests. Sequential CPU profiles, request-shape analyses, critical paths and restored engine state are included.

Each capture keeps the original compressed dump chunks. After extraction, run `python3 evidence/assemble-traces.py evidence/capture-candidate` or replace the final path with `evidence/capture-before`. This recreates the combined trace and verifies its exact bytes and SHA256. Raw combined files are omitted from the archive to avoid duplication. MANIFEST.json verifies every included member and the archive.

The unchanged engine and CLI sources are in the preceding [typed metadata experiment](../typed-artifact-metadata/). The module commit is 0b48743446cd6121f71141598022bc69700dbf26, based on the existing ownership prototype 7568cd0. Original local paths and the local telemetry receiver require adapting for replay. Engine binaries, credentials and the retained volume are excluded. No PR is open.
