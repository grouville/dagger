# perf(fsutil): reach literal imports without enumerating sibling directories

Importing one host path enumerates unrelated siblings at each ancestor. Go collection discovery repeats these filtered imports, so a selected file can incur work proportional to its surrounding directories.

Let the native filesystem reach a single literal include directly, feeding its ancestor records and selected subtree through the existing filter. Symlink, missing or unreadable ancestors fall back to the ordinary walk. This is part of reducing Go test collection listing overhead on dagger/dagger.

### Performance

Complete-command measurements use `dagger check --module go --check test --list --all`.

| Complete listing | Before | After | Reduction |
| --- | ---: | ---: | ---: |
| Command time | 55.81 s | 52.03 s | 6.8% |
| CLI CPU | 39.50 CPU-s | 26.81 CPU-s | 32.1% |

Two alternating pairs, both faster. Fresh CLI processes edit source on the same warm experimental engine, with telemetry and successful cleanup included. All six commands succeed; measured listings contain identical 4,398 rows. Initialization, including a real test addition, is separate.

A three-level literal path surrounded by 8, 128 and 2,048 siblings takes **57 µs, 194 µs and 2.44 ms** before, versus approximately **50 µs** in each case afterward. At 2,048 siblings allocation falls **576 → 15 kB**. A diagnostic real-repository run visits **5.58 million → 237,287 entries**.

### Validation and tradeoffs

The fsutil and client race suites pass. Tests compare full metadata and order, including hardlinks, symlinks, missing paths, permissions, xattrs, exclusions, callbacks and cancellation. Existing Go collection checks pass.

There is no shared state, lock or metadata-format change. The populated /tmp amplifies the benefit on this host; the command numbers are not a clean-host or cold-start estimate. Other filesystem implementations retain their walker.

[Source](https://github.com/grouville/dagger/commit/c22eaa55863fb2ca22919119ff30e952f54f8076). [Measurements and reproduction](https://github.com/grouville/dagger/blob/experiment/rust-native-cache/hack/rust-cache/NATIVE_FILESYNC_LITERAL_WALKS.md).
