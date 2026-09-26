# Independent final review

Reviewed commit `4b488e191f`, `hack/collections-ux-performance.md`, and the saved `vertical-local-disk-v3` driver, provenance, 79 result rows, phase summaries and profiler headers. No workload or build was run.

## Material wording corrections

1. **Command count attribution:** the complete matrix contains 79 validated commands: 37 baseline and 42 candidate, including five candidate profiles. Change “The production CLI completed 79 validated commands” to “The comparison matrix completed 79 validated commands.” There are 77 successful exits and two deliberately failed check invocations; all correctness assertions pass.
2. **Warm generation is already current:** all six measured warm generator rows report `file_already_current_at_start=true`, with no new-byte visibility sample. Say explicitly that warm generation validates an already-current output. All edited generator rows require new bytes, and every export removes its destination first and writes it again. Avoid presenting the warm generator number as write latency.
3. **First recorded operation, not engine arrival:** 126 ms is the offset of the earliest recorded wcprof operation. It does not establish first request arrival or exclude earlier uninstrumented engine work. Replace “first reaches the engine after 126 ms” with “its first recorded engine operation begins after 126 ms.” The 216 ms `dang.invoke` observation is an interpreter callback under `Check.sync`, including dispatch, rather than a timestamp of the first authored source instruction.

## Verified claims and boundaries

- Every warm/edit median in the document matches an independent recomputation from `results.json`. The service row uses first observed correct HTTP response; other rows use full CLI exit.
- The saved driver hash matches provenance. Its selected candidate hash is `0c841d64a3aad06b082ad9bb0beb618f6d07e86e8ce83008e5621e7b878e86bb`, the separately validated production binary.
- All five profiler headers report zero dropped events and no open operations. The first recorded check operation is 126.007 ms, interpreter callback under Check.sync is 215.615 ms, full profiled exit is 259.359 ms. Last-recorded-operation-to-exit gaps range from 9.763 to 22.583 ms. They are correctly separated from unprofiled latency samples and not assigned wholly to telemetry.
- The local-only/retained-engine caveats, small three-pair sample caveat, unaffected-command variability, and separation from Kyle's cold and normal Cloud-enabled timings are appropriate.
- File visibility is observation of expected bytes, not a durability/fsync claim. The 5 ms readiness polling interval is nominal; an HTTP attempt can additionally wait up to its 100 ms timeout. The code verifies tunnel closure after intentional cancellation.
- The single non-Git recovery and local scaling microbenchmarks are correctly presented as separate evidence, not a general whole-command percentage or cold-start distribution.

## Upstreamability

No blocking source issue found. All three committed files exactly match the validated production sources. The fix removes a demonstrably unnecessary whole-destination enumeration while preserving asynchronous completion, relevant timestamp operations, merge/deletion protocol and static symlink/replacement behavior. Its memoization is scoped to one flush and does not change Dagger cache freshness. The private helper keeps the patch scoped to DiskWriter; the snapshot path remains a separate change.

The report appropriately discloses that native Windows semantics tests were not executed here. The portable ancestor recursion avoids the absolute-root spelling termination issue; no stronger concurrent pathname-race guarantee should be claimed. The current implementation records only newly created directories for deferred timestamp finalization, preserving the existing handling of already-existing directories.
