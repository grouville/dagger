# perf(clientdb): allocate spill buffers when needed

Opening a telemetry spill file allocates a 64 KiB recovery reader and a 64 KiB writer, including when the file contains only its header. Recognize that empty case without a scanner and create the writer on the first valid nonempty append.

File creation, header validation, populated-file recovery and append flushing keep their existing behavior. Closing an unused store still closes the file. The existing single writer owns buffer initialization; no lock or storage-format change is needed.

Four alternating benchmark pairs on Go 1.26.6: empty open/close improves **25.10 → 7.54 µs**, with allocation **131,920 → 536 bytes**. Opening populated stores also allocates about 64 KiB less. The first-append control includes open, a real write, flush and close: **32.00 → 24.23 µs**, faster in all four pairs.

On the experimental collection stack, fixed eight-pair complete-command comparisons are **7.15 → 7.00 s** after a test edit (6/8 faster), and **4.15 → 4.19 s** after an ordinary-source edit (3/8). Test-edit allocation falls **6.36 → 5.61 GB**. This is primarily an allocation improvement; the latency effect is not uniform. Timings include telemetry and successful cleanup.

The full clientdb race suite passes before and after, including an empty close/reopen/append recovery test. The diagnostic engine also passes its exact-overlay race suite, 27 Go checks and 28 Rust/native-cache cases with their expected outcomes. [Source, all cohorts and first-write measurements](NATIVE_TELEMETRY_LAZY_BUFFERS.md).
