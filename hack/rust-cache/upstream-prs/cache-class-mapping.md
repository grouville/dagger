# perf: avoid sorting live cache classes during compaction

Cache compaction holds the graph lock while finding live class IDs, sorting them and building an old-to-new ID map. Those IDs already index the parent table. Marking them in a bitmap and counting preceding live bits produces the same consecutive IDs without the two hash tables or sort.

Four alternating pairs per populated-cache shape, with 50,000 cached results:

| Compaction | Before | After |
| --- | ---: | ---: |
| Independent results | 139.51 ms | 119.88 ms |
| Shared receiver | 160.79 ms | 139.66 ms |

All eight pairs improve, with about 3.53 MB less allocation. The index is rebuilt inside each timed operation; fixture construction and validation are excluded. Ordinary GC stays enabled. This measures compaction and its graph-lock hold, not complete-command latency.

A larger symbolic fixture improves 1.143 → 0.938 seconds. A sparse million-slot fixture improves 5.418 → 4.742 ms but allocates about 40 kB more: temporary bitmap storage follows the allocated ID range. A simpler full-size array was rejected because it slows that sparse case and adds 7.8 MB.

The graph lock, collection policy, stored format and resulting ID order are unchanged. Only standard-library bit operations are added. The boundary regression and existing merge, index, persistence and cache-hit tests pass; the full DagQL race suite passes on the standalone branch. The populated-cache benchmark also checks unchanged live counts, valid indexes and a cache hit after compaction.

[Measurements, tradeoffs and retained evidence](../NATIVE_CACHE_CLASS_MAPPING.md). No full-listing speedup is claimed, and the retained diagnostic engine has not been changed.
