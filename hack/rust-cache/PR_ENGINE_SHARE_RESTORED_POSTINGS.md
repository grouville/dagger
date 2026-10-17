Restarting an engine expands each persisted output class into a separate result set for every digest in the class. A class with D digests and R results therefore allocates D × R tree nodes.

The populated Go discovery cache exposed the cost: 198,689 stored results expanded to roughly 394 million associations. One class accounted for 379 million. An idle heap profile attributed about 18 GB to the restored index.

Share one snapshot of each imported class's results across its digests. Keep later additions separate for each digest. The snapshot does not follow later class merges, and collecting a result removes it from every imported alias. Lookup still orders candidates by result ID. There is no persistence-format change or new lock.

Fresh cache objects reopened the same on-disk fixture in three alternating before/after pairs, with a warm filesystem cache:

| Restored results | Import before → after | Allocated before → after |
| --- | ---: | ---: |
| 129 | 7.62 → 5.39 ms | 2.41 → 1.57 MB |
| 513 | 44.46 → 13.16 ms | 19.05 → 6.25 MB |
| 2,049 | 690.37 → 45.11 ms | 227.81 → 25.61 MB |

The benchmark verifies the restored result count and that import did not reset the store. Shutdown is outside the measured interval. The index's construction and storage become proportional to D + R rather than D × R.

The full DagQL race suite passes. The added test checks that merging classes does not broaden old postings, an exact addition stays local to its digest, and collection removes a shared result. Existing tests cover expiry, resource requirements, persistence, compaction and pruning.

On the diagnostic engine, the existing cache survives a graceful restart and all six native Rust histories retain their compiled actions. Go listing returns identical 4,398 rows and exits successfully twice. Its median remains 66.14 s: this change fixes restored-index memory and construction cost; it does not solve full-repository discovery latency.
