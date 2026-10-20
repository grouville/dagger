# Why use a bounded LRU for configuration parsing?

DagQL can cache these parsed declarations. Its ordinary module-function cache does not automatically remove this work: `ModuleFunction` reads declarations while preparing the inputs that determine the module call's cache identity. A separate cached parse keyed by the current bytes is required either way. Reading the file and selecting the nearest configuration must still happen on every lookup.

The existing `dagql.Cache.GetOrInitArbitrary` API is an appropriate alternative for an in-memory value. It can share entries across overlapping sessions, tracks their session ownership, and removes an entry when the last owning session ends. It does not persist or export these values. A focused check verifies one decode for repeated lookups within a session and a new decode after that session is released. The current LRU is also in memory only, retains entries across non-overlapping commands, and has a fixed 32-entry limit with bypass above 64 KiB.

The isolated comparison uses the exact PR source `f2a21f27edf64b2d9a00e06e61ddb29e3a500292` on main `ce6dc9f9403b52067f5831149eab4871f857185d`. Both variants hash the same actual 1,649-byte configuration, return the same immutable derived declarations, deliver warnings and clone returned slices. The DagQL prototype uses a namespaced SHA-256 string key and the existing arbitrary-value API. Four alternating fresh-process pairs per case, 5,000 lookups per process, GOMAXPROCS=8. Setup, session release and cache close are outside the measured region. No other heavy job runs concurrently.

| Parsed-content reuse | Bounded LRU | DagQL arbitrary cache | Allocations, LRU → DagQL |
| --- | ---: | ---: | ---: |
| Repeated bytes | 4.3465 µs | 4.635 µs | 0 → 6 |
| Repeated bytes, eight workers | 1.3225 µs | 1.620 µs | 0 → 6 |
| Distinct bytes every lookup | 346.490 µs | 373.3685 µs | 2,823 → 2,837 |

These measure parsing/reuse after reading bytes, not the complete `DeclaredGitClients` function or a CLI command. Their numbers must not be substituted into the existing PR's full-function table. Concurrent results are time per completed lookup across workers. The prototype has no attached live engine/client scope, so it is not an integrated replacement. The timings do not justify an end-to-end advantage for choosing LRU over DagQL. Both avoid the expensive repeated parser work.

Keep the current bounded LRU for the smaller integration: the shared configuration package already accepts an ordinary file reader and can run without engine/session state. Using DagQL here would require supplying that state or moving the parsing/cache boundary into core. DagQL's arbitrary cache also has session retention rather than the explicit entry bound of this helper. Neither alternative is a compilation-result cache, and neither changes ordinary module-function cache identities.

This is a design choice, not a claim that DagQL cannot do it. If later work gives parsed configuration a natural place in the engine's result graph, that may change the trade-off. The PR implementation remains unchanged; its existing race/correctness checks still cover the published source.

Raw samples, commands, stdout/stderr, prototype and lifetime check accompany this report. The first harness attempt mixed cache-close log records into benchmark stdout and could not parse the result row. It is retained in `harness-attempt01`, excluded from the comparison. The corrected harness separates stderr and explicitly stops the timer before teardown.
