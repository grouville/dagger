# core: prune native glob walks by directory prefix

`Directory.glob("module/**/*.go")` currently walks unrelated modules. Its existing shortcut only handles patterns whose trimmed form has no wildcard. Repeating scoped globs over a large native snapshot repeats most of the filesystem traversal.

Keep walking from the original root, but skip directories outside the fixed directory prefix before the first pattern character. The matcher, path order, symlink handling and API-dependent directory suffixes stay the same. Global and exclusion patterns retain their full walks. This is the same pruning rule already tested in the CLI's host glob implementation, with no new API, cache or lock.

Four alternating component pairs on a 4,608-file fixture, running the actual native `Directory.Glob` method with a local storage adapter:

| Pattern | Before | After |
| --- | ---: | ---: |
| `module00/pkg00/*_test.go` | 8.59 ms | 88 µs |
| `module00/**/*.go` | 8.76 ms | 555 µs |
| `**/*.go`, full-tree control | 12.37 ms | 12.61 ms |

Scoped cases improve in all four pairs; the global control is mixed. On the native-directory Go prototype, sampled glob CPU falls **3.17 → 0.17 CPU-seconds**. Complete source-edited listing moves **4.80 → 4.41 s** (3/4 faster), while test-edited listing is mixed at **8.42 → 8.17 s** (2/4). The selected module also has mixed timings, so this is not a claim of a general listing speedup. Fresh CLIs, telemetry and cleanup are included on a warm experimental engine. No cold-start result is established.

Parity tests compare exact results and order against a deliberately unpruned walk, including wildcard tails, escapes, Unicode, symlinks, exclusions, cancellation, invalid patterns and missing paths in both directory-suffix views. The focused race suite passes on current main and the experimental engine. The existing real-snapshot glob integration suite passes in both modes with distinct inputs. All 32 public Go checks, 28 Rust/native-cache cases and 48 timed listings have their expected outcomes. Profiles retain all authored getters and normal discovery reuse.

[Source, complete measurements and attempts](NATIVE_DIRECTORY_GLOB_PREFIX.md).
