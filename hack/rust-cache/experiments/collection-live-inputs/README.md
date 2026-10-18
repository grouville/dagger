# Live collection inputs

See [the assessment](../../NATIVE_GO_COLLECTION_INPUTS.md). A frozen-name diagnostic changes 11.92 → 1.07 seconds median when an unused child Workspace argument is removed. Lossless captures verify 800 child executions become 800 cache hits. This does not establish fresh-source discovery or a real Go-module improvement.

The archive includes both exact frozen sources, all ten full-command observations, separate lossless captures and execution counts. The real owner-index experiment is rejected after 17.61 → 19.05 seconds; its source patch, four focused passing checks, initial constructor error and all ten observations are retained. A prepared remaining-check driver was not run after rejection. CPU attribution and a separate allocation capture explain why neither an ownership scan nor schema cloning is established as the next major cost. The allocation profile covers fewer bytes than memstats; its percentages are not whole-command shares.

Lossless original dump records are stored as raw `chunk-*.ndjson` files inside this archive. After extraction run `python3 evidence/attribution/assemble-traces.py evidence/attribution/capture-child-no-workspace`, replacing the final directory with `capture-child-workspace` or `capture-allocations` as needed. The combined trace's exact size and SHA256 are checked. Duplicate combined trace files and gzip wrappers are omitted.

MANIFEST.json verifies every archived file. The unchanged engine and CLI sources are in the [typed metadata experiment](../typed-artifact-metadata/); the selected real module is the [batched discovery baseline](../go-batched-discovery-facts/). Original local paths and the telemetry receiver need adapting for replay. Binaries, credentials and the engine volume are excluded. No PR is open.
