# Separate repeated preparation from occasional lease pauses

The grouped-hash follow-up contains one 1.419 s Cargo-configuration filter request. Its critical path puts 1.178 s in attaching a snapshot lease and 108 ms in copying files. The existing manager already writes an owner's lease, snapshot chain and blobs in one transaction. This is not evidence that transaction batching is missing.

A diagnostic overlay separates time before the metadata transaction's callback, the callback's lease mutations and time after the callback through `Update` returning. The last interval includes commit and metadata notifications; it is not a pure fsync measurement. Existing attach-lease concurrency, failure and blob-retention tests pass under race detection. A clean shutdown exits zero in 15.76 s before installing this diagnostic binary, preserving the volume.

Six fresh large-leaf captures alternate the two hashing implementations after preparation. They have no dropped events or open operations. The largest complete lease attachment is 4.17 ms; all observed transactions stay below 0.49 ms. Host I/O stalls remain below 6.6% and engine I/O below 0.22%. The earlier 1.178 s pause is not reproduced. These captures do not justify changing retention, locks or durability, nor establish the cause of that earlier pause.

## Time the actual Go module

Temporary instrumentation on `28dab90` times the Go compiler submodule's phases and its nested core API calls. Logs contain phase names, durations and query lengths. The existing local OTel receiver remains enabled. The extractor reads only the newly appended byte range and waits for asynchronous delivery. An earlier preparation-only attempt checked too soon for its second record; the complete six-capture run accounts for that delivery delay and restores module settings afterward.

Two fresh 1,026-crate leaf edits show:

| Phase | First capture | Second capture |
| --- | ---: | ---: |
| Read plan through API | 115.6 ms | 113.4 ms |
| Decode plan JSON | 34.8 ms | 36.0 ms |
| Validate Cargo configuration | 203.1 ms | 240.5 ms |
| Read source path list | 35.1 ms | 63.7 ms |
| Hash package directories | 200.0 ms | 203.5 ms |
| Select retained results | 7.8 ms | 9.2 ms |
| Construct execution graph | 24.8 ms | 20.9 ms |
| Synchronize compilation outputs | 633.3 ms | 556.8 ms |
| Retain checkpoint | 55.8 ms | 61.3 ms |

The graph's broader timer includes hashing and result selection. Synchronization includes real rustc work and engine preparation. These intervals overlap with their encompassing module and request spans, and must not be added twice or treated as unprofiled command medians.

A 130-crate leaf capture spends 19.3 ms reading the plan, 4.2 ms decoding it, 28.1 ms validating configuration, 45.8 ms hashing packages and 140.8 ms synchronizing compilation. Its Go function totals 284.3 ms. Two actual small-collection edits spend about 2.7–2.9 ms reading the plan and 276–279 ms synchronizing compilation. The separate test execution follows the compilation function. Thus the large plan-transfer cost does not describe the small collection.

The [plan-file transport experiment](NATIVE_PLAN_FILE_TRANSFER.md) follows from the repeatable plan-read cost but remains unselected after its mixed crossover. The [literal-display change](NATIVE_LITERAL_DISPLAY.md) independently removes a quadratic formatter while retaining the complete displayed data; its command-level benefit still needs measurement.

The [data](experiments/native-preparation-phases/measurements.json) preserve six lease captures, their transaction breakdowns, I/O counters, all preparation and compiler-phase records, capture completeness and bounded telemetry ranges. The temporary Go and lease patches and their drivers are archived beside them. Neither diagnostic patch is a proposed production performance fix.
