This archive records a held cleanup-overlap correction to the held shared-HTTP/2 prototype. It is not applied to production source. Stack `source-evidence-v1/prototype.patch.txt` first, then `cleanup-overlap.patch.txt`; the latter only moves the fully joined physical owner Close into the existing cleanup group after cancellation.

The final serial-v1 negative witness fails exactly the parent test and its two expected subtests. The corrected focused normal and race suites pass. The first witness's synctest/HTTP2 pool contamination is retained as failed fixture history, with original witness source and numeric validation outcomes; raw logs remain private. The production correction did not change while the fixture was repaired.

Three CLIs were freshly compiled from identical HEAD0d source, original otel dependency bytes and flags. Original keeps separate pools and three warm tunnels. Shared-serial and shared-concurrent both retain the same per-client owner, request cancellation, pending-dial joining and two warm tunnels; only cleanup scheduling differs between those two. No engine binary was rebuilt for this comparison.

The 54-command local comparison did not establish a performance repair. Warm generation medians were 251.4 ms original, 272.2 ms shared-serial and 282.2 ms shared-concurrent; the concurrent version was slower than original in all three triples. Both prototypes remain held. Full results and limitations are in `cleanup-runtime-v1/evidence-v2`, while the earlier broad 90-command comparison remains separately preserved.

All mandatory waits remain. No timing benefit may be claimed by allowing physical subprocess cleanup to escape after CLI exit. The tests prove cleanup overlap and joining, not production latency improvement.
