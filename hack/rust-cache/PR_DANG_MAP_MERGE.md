# perf: merge maps with one copy

`Map.merge` copies the accumulated map for every incoming key. Merging two similarly sized maps therefore takes quadratic time. Copy the left map once, then apply the right map in order.

The result keeps existing key positions, appends new keys in right-hand order and lets right-hand values replace existing ones. Inputs remain unchanged. Empty-right merges retain their existing behavior. No cache, lock or dependency is added.

Four alternating benchmark pairs on Go 1.26.6, with eight available processors:

| Keys in each map, disjoint | Before | After | Allocated bytes, before → after |
| --- | ---: | ---: | ---: |
| 8 | 8.03 µs | 1.08 µs | 10,880 → 1,496 |
| 128 | 1.10 ms | 12.89 µs | 1,968,262 → 23,384 |
| 512 | 18.31 ms | 59.50 µs | 33,041,733 → 100,480 |

All 24 pairs improve, including fully overlapping maps. The full interpreter race suite passes with both implementations. Tests cover ordering, replacement, empty and self merges, type preservation and independence of the result's storage.

This is a component improvement. Complete Go collection listing is effectively flat with this change alone; no listing speedup is claimed. [Source, measurements and scope](NATIVE_GO_DIRECTORY_MEMBERSHIP.md).
