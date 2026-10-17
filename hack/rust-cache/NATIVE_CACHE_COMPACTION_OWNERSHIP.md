# Reuse owned data while compacting the cache index

The candidate remains a component experiment. It does not establish a faster complete Go listing and is not installed in the selected engine.

The preceding [host-request profile](NATIVE_CONFIG_HOST_REQUESTS.md) aligned a roughly 7.3-second publication stall with cache-index compaction under the same graph lock. Compaction allocated about 1.46 GB in that capture. The implementation being measured is byte-identical to the corresponding upstream method.

Two variants remove copies under the existing lock. The first moves unchanged digest sets into the new outer class-ID maps. The second also rewrites each term's privately owned input slice in place. Neither changes the lock, collection policy, cache budget or persisted format.

Four balanced triples run each shape in fresh processes with ordinary GC and `GOMAXPROCS=8`. Fixtures contain two digests and two two-input terms per live class, with an extra digest on every eighth class. Construction and validation are outside the timer. These symbolic index fixtures have no materialized result rows and are not a substitute for measuring the retained engine cache.

| Fixture | Original | Reuse digest sets | Also reuse term inputs |
| --- | ---: | ---: | ---: |
| 1,000 live / 1,000 dead classes | 4.02 ms | 3.14 ms | 2.90 ms |
| 200,000 live / 40,000 dead classes | 1.201 s | 1.113 s | 1.113 s |
| 2,000 live / 1,000,000 dead classes | 5.55 ms | 5.08 ms | 5.19 ms |

On the large fixture, allocation falls from 299.53 MB to 238.32 MB with digest-set reuse and to 231.92 MB with both changes. The latter removes about 850,000 allocations and is faster in all four large-fixture pairs, but adds no established time benefit over the smaller change. This is a bounded maintenance improvement, not the order-of-magnitude collection improvement being sought.

A focused race check passes on the original and combined variants. It retains a persistence snapshot, compacts, merges classes, compacts again, checks the captured rows remain unchanged and verifies the dependent result still hits its cache. The ownership audit checks persistence, debug and remote-export readers copy the data they retain outside the graph lock. Broader actual-cache and full-command validation are still required before selection or an upstream proposal.

The ongoing investigation also follows [scalar metadata projection](NATIVE_COLLECTION_SCALAR_PROJECTION.md), because reducing the number of results that require graph bookkeeping may matter more than making maintenance of those results cheaper. The complete Go listing remains about 40–45 seconds on the retained engine; no new full-command gain is attributed to compaction.
