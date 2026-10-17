Filtered host imports enumerate unrelated siblings at every ancestor of the selected path. Parent-directory synchronization repeats this for each content snapshot, making imports slower when surrounding directories contain many entries.

Let the native filesystem reach a single literal include directly, while feeding its ancestor records and selected subtree through the existing filter. Symlink, missing and unreadable ancestors fall back to the ordinary walk. The metadata format and normalization stay the same; there is no new shared state or lock.

Complete Go test collection listing on `dagger/dagger`, in two balanced pairs:

| Metric | Before | After |
| --- | ---: | ---: |
| Complete command, median | 55.81 s | 52.03 s |
| CLI CPU, median | 39.50 CPU-s | 26.81 CPU-s |

Both pairs improve. All six commands exit successfully. An initialization pair adds a real test and returns identical 4,399 rows; measured pairs remove it and return identical 4,398 rows. Each command starts a fresh CLI and edits the source on the same warm experimental engine, with telemetry and ordinary GC enabled. Both CLIs retain the same earlier glob and output-buffering changes.

For a three-level path surrounded by 8, 128 and 2,048 siblings, component medians change from 57 µs, 194 µs and 2.44 ms to approximately 50 µs in all cases. At 2,048 siblings, allocation falls from 576 to 15 kB. A separate real-repository diagnostic reduces visited entries from 5.58 million to 237,287. The populated `/tmp` amplifies the cost on this host; these figures are not a clean-host latency estimate.

The fsutil and client race suites pass. Tests compare full metadata and order with the original walker, including hardlinks, symlinks, missing paths, permissions, xattrs, exclusions, callbacks and cancellation. Existing Go collection checks pass. [Complete measurements and reproduction details](https://github.com/grouville/dagger/blob/experiment/rust-native-cache/hack/rust-cache/NATIVE_FILESYNC_LITERAL_WALKS.md).
