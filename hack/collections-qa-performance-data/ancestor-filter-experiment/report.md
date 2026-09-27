# Parent synchronization: bounded traversal results

An isolated prototype makes parent-only traversal independent of unrelated siblings. This establishes an algorithmic opportunity; it is not a measured improvement to a Dagger command. No production source was changed.

| Unrelated siblings at each of four levels | Existing median | Gated chain median | Allocated bytes/op before → after |
| --- | ---: | ---: | ---: |
| 0 | 32.17 µs | 47.91 µs | 4,838 → 5,505 |
| 100 | 470.53 µs | 46.90 µs | 108,552 → 5,649 |
| 1000 | 4633.68 µs | 46.68 µs | 1,003,573 → 5,649 |

Five repetitions per variant, 250 ms benchmark duration, one Go process, GOMAXPROCS=4, Linux/amd64. The eligible ext-family gate is asserted and included in these timings. Subtests group general then candidate repetitions; they are not randomized paired engine measurements.

The empty-width case gets slower: the conservative filesystem gate costs more than it saves on an already tiny traversal. At width 1,000 the existing walker visits 4,003 entries; the candidate visits only the root and three selected ancestors. Its traversal performs four explicit lstats and four directory-open checks. Emission also performs three fresh Info stats (and existing metadata/xattr work), and the gate adds three open/fstatfs/ioctl/close sequences. Those are distinct costs: 4+4 is not the total syscall count.

This test host is unusually wide: the parent separately observed 5,996 entries in /tmp, 332 in /tmp/collections-perf, 86 in /home/dagger, 72 in the benchmark lab and 24 in greetings. The accumulated experiment artifacts can amplify this bottleneck. Do not project the saved CLI sender CPU or these synthetic ratios onto a normal small user checkout.

Six focused test groups pass normally; those six plus the existing filter regression group pass with the race detector. Tests force the new traversal for semantic parity independently of platform eligibility; the Send protocol test additionally exercises the production gate. They cover ordered stat/data packets, normalization and ignored flags, lazy parent emission, fresh metadata, missing/replaced/symlink paths, cancellation, skip callbacks and read permissions. The baseline-negative test is only an activation/wiring witness: unchanged NewFilterFS does not select the chain implementation. It is not evidence that the legacy behavior is functionally incorrect.

The generic filter optimization remains held: exact directory-entry spelling requires the Linux/ext/no-casefold gate, and opening a directory does not reproduce I/O faults reported only by enumerating its contents. Those are genuine portability/contract limits. A dedicated internal parent-metadata request is the preferred next prototype: specify fresh literal ancestor lookup under existing filesync authority, preserve a compatible legacy fallback, and avoid silently changing a generic filter contract.

No snapshots or stats are retained across calls. Actual subtree imports, source invalidation, cache identity and public CLI UX are unchanged by the isolated code. The next proof must run real imports/listing/edits with the explicit request candidate, not infer a full-command saving from this microbenchmark.
