# Full Go listing: separate the client from engine work

The latest selected full-listing comparison remains **53.58 → 46.72 seconds**, with identical 4,398 rows. Neither [native sorting](NATIVE_DANG_STRING_SORT.md) nor [span-resource reuse](NATIVE_SPAN_RESOURCE_BATCHES.md) establishes a further reliable latency improvement. Both remain unselected.

A new complete diagnostic lists the same 4,398 rows and exits successfully in 43.04 seconds. This is a profiled observation, not a replacement benchmark or an improvement claim. It enables the resource-reuse candidate temporarily and restores it to off afterward.

## Where the complete command waits

Wcprof retains 559,749 events, with none dropped or left open. On the main query's critical path:

| Phase | Diagnostic observation |
| --- | ---: |
| Discover packages | 17.20 s |
| Finish expanding test collections | 30.65 s from query start |
| Read and publish collection metadata | About another 10.8 s |

The first two phases are sequential; the second row is an offset, not an additional 30.65 seconds. The command still makes 963 Dang invocations. Their elapsed durations include awaited API work and must not be described as interpreter CPU.

## Client CPU is spread across several paths

The CLI uses 23.83 user and 4.84 system CPU-seconds. Fourteen completed three-second CPU windows contain 26.18 sampled CPU-seconds. There is no Go runtime trace, forced GC or engine CPU sampler in this capture.

| Cumulative client frame | Sampled CPU |
| --- | ---: |
| Filesystem import handler | 3.97 s |
| Host glob handler | 1.39 s |
| UI event dispatch | 3.80 s |
| Telemetry payload consumption | 2.56 s |
| Background garbage collection | 4.39 s |

These frames can overlap with their descendants; they are not additional wall-time phases. They do not identify one CLI fix capable of removing most of the command. The earlier selected filesystem fixes remain useful, but client CPU alone does not explain the roughly 30 seconds spent evaluating discovery.

The final in-flight CPU-profile request loses its connection when the CLI closes its debug server just before exit. Its incomplete window is excluded. All fourteen complete windows, their offsets, the command's successful exit and the original capture error are retained. The corrected filesystem report anchors package names: a broad `filesync` filter also matched the checkout directory and therefore included unrelated frames.

The next investigation follows collection metadata materialization. Wcprof records 17,592 synthetic dimension-key element reads, 4,398 artifact element reads and substantial cache-publication work. Synthetic element reads inherit the containing field's name; they do not imply that field's resolver runs once per element. Any faster path must preserve addressable object IDs, ownership and session behavior; the earlier unconditional uncached-list attempt failed its ID test and remains rejected.

[The archive](experiments/go-cli-post-resource-profile/) contains the complete command, CLI CPU windows, source identities, wcprof, samples, derivation commands and restored engine state. There is no active session, profiling is off, the selected span index is on, and both resource reuse and lazy Type maps are off. No PR is opened.
