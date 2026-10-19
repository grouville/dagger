# patternmatcher: reject impossible suffixes before regexp matching

Patterns such as **/*.go currently run their regexp against every candidate path, including paths that do not end in .go. Host-glob profiles show this consuming about 0.4 CPU-seconds during Go collection listing.

Record a conservative literal ASCII suffix when compiling the pattern, then reject impossible endings before running the existing regexp. Escapes, character classes and Unicode endings retain the general path. The ASCII restriction preserves matching of malformed UTF-8 paths. Exclusions, compilation errors and possible matches keep their existing behavior.

The patch adds 13 production lines. Four alternating component pairs reduce rejection of a long nonmatching path from **5.25 µs to 9.24 ns**, with no per-match allocation. Matching paths remain broadly unchanged. The tradeoff is one string field per pattern, a compile-time scan and a suffix check for possible matches.

On complete dagger/dagger test-edited listing, the same warm experimental engine and CLI move **6.93 → 6.69 s median**, faster in all four pairs. Source-edited listing moves **4.03 → 3.96 s**, faster in three of four pairs. CLI CPU falls in all eight pairs. Commands start a fresh CLI and include telemetry and cleanup. These are CLI-only experimental-stack measurements; no cold-start, engine or Rust latency gain is claimed.

Pattern-matcher and host-glob race checks pass. Parity tests compare with the original regexp, including Unicode, invalid UTF-8, escapes, character classes, exclusions and path depths. All 27 Go checks, 28 Rust/native-cache cases and 24 complete timed commands have their expected outcomes. Four lossless profiles retain all 800 getters and the same discovery reuse.

[Source, measurements and limits](NATIVE_GLOB_LITERAL_SUFFIX.md).
