# TreeSet iteration: fewer allocations, limited listing impact

A one-file change in the existing `hashicorp/go-set` library makes full iteration **6.7–7.1× faster** on the larger fixtures. It is a library candidate, not an established improvement to the complete Go listing. The selected engine is unchanged.

## Work removed

`TreeSet` traverses its nodes using a private linked stack. Every push allocates a stack entry; a full traversal therefore allocates once per visited node. Both Dagger's pinned `v3.0.1` and upstream `0a1b2f9a` use that implementation.

The change stores the same pending nodes in a slice. Popping clears the vacated slot so the backing array cannot retain the popped reference. The original iterator, prefetch order and callbacks remain unchanged. Allocation now follows stack growth, bounded by the tree height, rather than the number of visited nodes. There is no new dependency, lock, cache, public API or persistence format.

An initial experiment using the existing recursive traversal passed the library race suite. It was not selected or timed: changing only the private stack preserves more of the original behavior.

## Fixed four-pair comparison

Four alternating fresh-process pairs use copies of the pinned library that differ only in `stack.go`, Go 1.26.6, eight Go workers, ordinary collection and 200 ms per benchmark. Tree construction is outside timing. Both complete iteration and stopping after the first item are measured.

| Full traversal | Linked stack | Slice stack | Allocations before → after | Bytes before → after |
| --- | ---: | ---: | ---: | ---: |
| 1 item | 26.00 ns | 26.09 ns | 1 → 1 | 16 → 8 |
| 8 items | 205.25 ns | 108.30 ns | 8 → 3 | 128 → 56 |
| 128 items | 3.699 µs | 0.554 µs | 128 → 4 | 2,048 → 120 |
| 4,096 items | 123.662 µs | 17.354 µs | 4,096 → 5 | 65,536 → 248 |

The larger traversals improve in all four pairs. This is not a win for every case. Reading only the first item of an eight-item tree slows **75.10 → 90.34 ns**, and allocates 56 instead of 48 bytes. Stopping after the first item of a 4,096-item tree improves **275.40 → 188.00 ns**, but slice growth allocates **248 instead of 176 bytes**. Empty first-only iteration changes 1.26 → 1.83 ns without allocating. These tradeoffs remain part of the assessment.

The pinned library passes its full race suite with an added check for sorted iteration, early stopping and repeated iteration across empty and larger trees, with both comparator directions. The current upstream library race suite also passes. Dagger's full DagQL race suite passes with the pinned library change and its original cache representations. An attempted dependency overlay was rejected by Go's module-cache restriction; the successful tests use separate local dependency copies and modfiles. The module cache was never edited.

## Relevance to the real command

The [saved real listing](NATIVE_CACHE_COMPACTION_INDEXES.md) provides an allocation profile without compaction. Subtracting its starting allocation profile attributes **163,842 of 251,656,968 sampled allocation objects**, about **0.065%**, to the linked-stack push. This is sampled cumulative allocation accounting, not retained heap or elapsed command time.

That fraction does not support treating this change as a major listing improvement. The same profile places about 4.67 GiB cumulatively in Dang function calls and 0.79 GiB directly in log `ForceFlush`, out of 24.58 GiB sampled allocation. Those frames overlap other entries and cannot be added as independent costs. They identify more consequential work to examine next.

A separate two-pair inline-ID prototype reduces singleton construction **105.10 → 31.34 ns**, using 24 instead of 128 bytes, but construction of two-member sets slows **150.25 → 214.75 ns** and adds two allocations. It remains unselected; the real workload's set cardinalities and complete-command effect are unmeasured. No new cache representation is installed.

[Prepared library description](upstream-prs/treeset-iterator-stack.md). [Verified evidence](experiments/cache-treeset-iteration/) contains the exact patch, both pinned dependency copies, every measurement, checks and real-profile reports. [Inline-ID evidence](experiments/cache-small-id-sets/) retains the separate experiment. Both are tracked on the Dagger fork; no library fork or PR has been created.
