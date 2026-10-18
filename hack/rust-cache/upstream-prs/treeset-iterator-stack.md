# Use a slice for TreeSet's iterator stack

Full TreeSet iteration currently allocates one linked-stack entry per visited node. Replacing that private stack with a slice reduces a 4,096-item traversal from 124 to 17 µs and from 4,096 allocations to 5 in four alternating benchmark pairs.

Only `stack.go` changes. The existing iterator keeps its traversal and prefetch order. Pop clears its vacated slot to release the reference. The stack now grows with pending traversal depth, while the public API and tree operations stay the same.

| Full traversal | Before → after | Allocations |
| --- | ---: | ---: |
| 128 items | 3.70 → 0.55 µs | 128 → 4 |
| 4,096 items | 123.66 → 17.35 µs | 4,096 → 5 |

Go 1.26.6, eight workers, ordinary collection, construction outside timing, four balanced pairs. Singleton traversal time is flat. Stopping after one item of an eight-item tree slows 75 → 90 ns; larger early-stop cases improve but can allocate more bytes during slice growth. The complete results are retained in the [assessment](../NATIVE_TREESET_ITERATION.md).

The library race suite passes on current upstream and on the pinned v3.0.1 source, including sorted iteration, both comparator directions, early stopping and repeated iteration. Dagger's full DagQL race suite also passes with the pinned-source change.

Prepared against `hashicorp/go-set` at `0a1b2f9adb417b8f14d4fdde67dc6bbe9f029d83`; the [patch and tests](../experiments/cache-treeset-iteration/iterator-stack.patch) are ready to review. This is a library change; adopting it in Dagger would require a compatible library release. No complete-command speedup is claimed and no PR is open.
