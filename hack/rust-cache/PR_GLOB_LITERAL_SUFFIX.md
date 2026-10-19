# perf(patternmatcher): reject impossible suffixes before regexp matching

Patterns such as `**/*.go` run their regexp against candidate paths that cannot end in .go. Host-glob profiles found about 0.4 CPU-seconds in this work during Go test collection listing.

Record a conservative literal ASCII suffix at pattern compilation, and reject impossible endings before running the existing regexp. Escapes, character classes and Unicode endings retain the general path. Restricting the shortcut to ASCII also preserves matching of malformed UTF-8 paths.

This is part of reducing Go test collection listing overhead on dagger/dagger.

### Performance

Complete-command measurements use `dagger check --module go --check test --list --all`.

| Complete listing after a fresh edit | Before | After | Faster pairs |
| --- | ---: | ---: | ---: |
| Test file | 6.93 s | 6.69 s | 4/4 |
| Ordinary source | 4.03 s | 3.96 s | 3/4 |

The test-edit reduction is **3.5%**. CLI CPU falls in all eight pairs. Each command starts a fresh CLI on the same warm experimental engine, with telemetry and successful cleanup included.

Four alternating component pairs reduce rejection of a long nonmatching path from **5.25 µs to 9.24 ns**, without per-match allocation. Matching paths remain broadly unchanged; the component ratio is not the command-level gain.

### Validation and tradeoffs

Pattern-matcher and host-glob race checks pass. Parity tests compare against the original regexp for Unicode, invalid UTF-8, escapes, classes, exclusions and path depths. All 27 Go checks, 28 Rust/native-cache cases and 24 timed commands have their expected outcomes. Profiles retain every package getter and existing discovery hit.

The production patch adds 13 lines. Its cost is one string field per pattern, a compile-time scan and a suffix check for possible matches. Cold-start and Rust latency effects are unmeasured.

[Source](https://github.com/grouville/dagger/tree/experiment/glob-literal-suffix). [Measurements and reproduction](https://github.com/grouville/dagger/blob/experiment/rust-native-cache/hack/rust-cache/NATIVE_GLOB_LITERAL_SUFFIX.md).
