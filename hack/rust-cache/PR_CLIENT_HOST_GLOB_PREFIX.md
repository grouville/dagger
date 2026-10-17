`Workspace.glob("core/*_test.go")` currently walks the entire host checkout. The existing shortcut handles literals and a final `*` or `**`, so it misses wildcard filenames. Listing tests across many packages repeats the same filesystem work.

Skip subtrees outside the literal directory prefix before the first pattern character. The walk still starts at the workspace root, preserving traversal order and symlink handling. Patterns without a fixed prefix keep their full traversal.

On the full `dagger/dagger` Go collection listing, two balanced pairs give:

| Metric | Before | After |
| --- | ---: | ---: |
| Complete command, median | 58.10 s | 53.76 s |
| CLI CPU, median | 75.96 CPU-s | 39.45 CPU-s |

All commands return identical 4,398 rows and exit successfully. Each starts a fresh CLI and edits the workspace on the same warm experimental engine, with telemetry and ordinary GC enabled. Both arms use the same Go module and CLI source; the host glob implementation is the only difference. An initialization pair is retained separately and excluded from the medians. Engine CPU and allocation remain comparable.

On a 4,608-file fixture, `module00/pkg00/*_test.go` takes 8.33 → 0.085 ms and allocates 1.24 MB → 22.6 kB per call. The full-tree `**/*.go` control takes 12.06 → 12.14 ms. These are medians of three alternating pairs.

The full client race suite passes. Added tests compare exact results and order against an unpruned walk, covering wildcard directory tails, character classes, escapes, Unicode, symlinks, absent prefixes and cancellation. Existing Go collection checks pass. Adding and removing a real test produces exactly 4,399 then 4,398 rows, with every other row preserved.

This removes repeated host filesystem work; full-repository listing still has substantial engine overhead. The change is confined to the host glob walker and introduces no shared state or dependency. [Complete measurements and reproduction details](https://github.com/grouville/dagger/blob/experiment/rust-native-cache/hack/rust-cache/NATIVE_HOST_GLOB_PREFIX.md).
