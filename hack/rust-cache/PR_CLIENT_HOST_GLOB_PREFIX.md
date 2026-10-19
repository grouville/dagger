# perf(filesync): prune host globs by their directory prefix

`Workspace.glob("core/*_test.go")` walks the entire host checkout. Its shortcut handles literal paths and a final * or **, but misses wildcard filenames. Go test discovery repeats this traversal across many packages.

Skip subtrees outside the literal directory prefix before the first pattern character. Traversal still starts at the workspace root, retaining the existing matching and order. Patterns without a fixed prefix keep the full walk. This is part of reducing Go test collection listing overhead on dagger/dagger.

### Performance

Complete-command measurements use `dagger check --module go --check test --list --all`.

| Complete listing | Before | After | Reduction |
| --- | ---: | ---: | ---: |
| Command time | 58.10 s | 53.76 s | 7.5% |
| CLI CPU | 75.96 CPU-s | 39.45 CPU-s | 48.1% |

Two alternating pairs, both faster. Every command starts a fresh CLI, edits source on the same warm experimental engine, returns identical 4,398 rows, and exits through normal telemetry and cleanup. Initialization is retained separately. Engine CPU and allocation remain comparable.

On a 4,608-file fixture, `module00/pkg00/*_test.go` improves **8.33 → 0.085 ms**, allocating **1.24 MB → 22.6 kB**. The full-tree `**/*.go` control is effectively flat at **12.06 → 12.14 ms**. Component medians use three alternating pairs.

### Validation and tradeoffs

The full client race suite passes. Parity tests compare exact results and order with an unpruned walk, covering wildcard roots and tails, classes, escapes, Unicode, symlinks, absent prefixes and cancellation. Adding and removing a real test changes listing by exactly the expected row.

The production patch is confined to the host walker, with no shared state or dependency. Two full-command pairs are limited evidence; they do not establish cold-start or clean-host performance.

[Source](https://github.com/grouville/dagger/commit/2481e74b3e02d185d9ba566199e5f4dfdca28eca). [Measurements and reproduction](https://github.com/grouville/dagger/blob/experiment/rust-native-cache/hack/rust-cache/NATIVE_HOST_GLOB_PREFIX.md).
