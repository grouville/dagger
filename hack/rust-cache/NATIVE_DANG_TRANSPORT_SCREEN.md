# Screen the native SDK transport before replacing it

Connecting the existing HTTP client and server through `net.Pipe` does not establish a useful gain. A two-request invocation slows **320 → 449 µs**, faster in only one of four pairs. Eight-request results are mixed. The prototype is rejected without changing the running engine or opening a PR.

Dang evaluates inside the engine, but each evaluated function creates a private loopback HTTP server and connection pool. The latest diagnostic records 3,898 invocations and 7,822 API requests. Those counts identify a candidate; they are not transport costs or predicted savings.

The first component screen calls the HTTP handler directly through a benchmark-only `RoundTripper`. It retains the real GraphQL client, request encoding and response decoding, but uses a trivial handler and does not model production lifecycle behavior. It gives a lower-cost reference, not an implementation ready to use.

| Requests per fresh invocation | TCP | Direct handler model | Faster pairs |
| --- | ---: | ---: | ---: |
| 0 | 24.52 µs | 0.10 µs | 4/4 |
| 2 | 320.70 µs | 10.84 µs | 4/4 |
| 8 | 795.09 µs | 44.69 µs | 4/4 |

A smaller candidate preserves `net/http` framing, response handling, cancellation and shutdown, replacing only the private connection factory with `net.Pipe`:

| Requests per fresh invocation | TCP | In-memory HTTP | Faster pairs |
| --- | ---: | ---: | ---: |
| 0 | 24.08 µs | 4.48 µs | 4/4 |
| 2 | 320.34 µs | 448.68 µs | 1/4 |
| 8 | 788.65 µs | 723.57 µs | 2/4 |

Each screen fixes four alternating pairs per request count, with normal Go GC and `GOMAXPROCS=8`. All 48 component measurements succeed. Existing shared SDK checks pass; the pipe screen also checks data transfer, canceled dials, closure and waking blocked operations. These tests do not prove production compatibility of the direct-handler model. No complete-command speedup is claimed, and multiplying component savings by invocation counts would not establish one.

The original lossless capture remains the better basis for choosing the next change. Its allocation delta attributes about 7.70 GB to reading and preparing decoded schemas, including repeated temporary input growth. That supports a separate temporary-buffer experiment without changing request ownership, cache freshness or telemetry. Allocation-profile deltas can lag GC and do not cover the command's exact allocation total.

[Sources, fixed observations and profile summaries](experiments/dang-inprocess-transport-screen/) preserve both screens. Their build overlays extend the exact engine sources archived with the [marker snapshot experiment](NATIVE_GO_MARKER_SNAPSHOT.md). No transport candidate is selected.
