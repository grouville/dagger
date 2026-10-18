# Interpreter context experiment

The candidate remains disabled: complete test-file-edited listing is 13.59 → 14.51 seconds and ordinary-source-edited listing 6.70 → 6.77 seconds, despite a roughly 200× depth-benchmark gain. Each workload has four balanced measured pairs and an excluded initialization pair. All 20 commands return correct ordered rows and exit successfully.

`evidence.tar.xz` contains exact interpreter candidates, tests, overlays, build and graceful restart records, all benchmark and command samples, verification logs, both lossless wcprof captures, CPU profiles and prepared analyses. `MANIFEST.json` verifies the archive and every member. Binaries, duplicate merged profiles and duplicate combined traces are omitted.

After extracting, `python3 assess.py` checks the cohorts, restoration, captures and trace identities. First run `python3 assemble-traces.py capture-before` and `python3 assemble-traces.py capture-candidate` to reconstruct the exact combined traces from the archived gzip chunks. `python3 analyze.py <capture>` requires the existing `/tmp/rust-cache-wcprof-report` tool. Prepared analyses are included.

Drivers refer to the original local development paths and persistent isolated engine. They are experiment records, not a standalone stock-main benchmark. The diagnostic engine inherits the previous `collection-getter-content` overlay and earlier experiments referenced there; its binary SHA-256 is `8a47fcb90387346a0c8b2e20c133af3c2968c8456d45b36f2c7e9e2dec9c45d2`. Both arms use Go module `09518aac0858390722e71c82a719c2f6e131e611`, getter content identity and typed artifact metadata. Telemetry and ordinary GC remain enabled. Profiling is separate from timing; some CPU windows extend past command exit.

`next-target-source/` records the code showing full collection receiver serialization and recursive Dang conversion for each getter. It motivates a scaling experiment; no gain from sharing that work is established yet. The isolated engine retains its existing volume and all switches are restored to disabled. The original Rust-cache engine is untouched. No PR is opened.
