# Minimal upstream patches

This review is source-only. No tests, engine calls or compilation ran during the parent's withFile benchmark. The shared checkout, frozen engine inputs and earlier successful privileged test artifacts remain unchanged.

## Container.withFile

`production-and-unit.patch` contains exactly:

- `core/schema/container.go`: choose the existing lazy operation when either destination or source has pending evaluation.
- `core/schema/container_source_lazy_test.go`: one ordinary host-compatible regression with new/restored subcases.

The production source is identical to the measured candidate (`3830c6713a88236b64c8004c221afbf2731035dca4f6f67010397a9d857359fd`). `git apply --check` passes against current HEAD `74d8b41823f06602ccfbf8fa7f58f1a1c8b7ada5`. The revised tests have NOT been compiled or executed yet. Use the new overlays here for that validation; the original test overlays still refer to the full privileged proof.

The regression uses the existing test store/cache helper. A real pending FileBlob with an invalid filename fails before any bind mount. A ready destination can construct `withFile`, read metadata and construct a Service without demanding that source; filesystem demand must surface its original error. The restored case captures the same pending operation, closes/reopens the cache and then exercises the same demand sequence. This verifies lazy dependency persistence without introducing custom test-only lazy codecs. Both cases are expected to fail unchanged production during withFile construction, as the original regression did; that baseline rerun is still pending.

Portability matters: existing `core/schema/demanded_read_test.go` and `lazy_stored_results_test.go` explicitly avoid read-only bind mounts in unit tests. The original full successful-copy tests need CAP_SYS_ADMIN; their privileged pass is valid evidence, but those test variants should not be committed to the ordinary schema package. The revised test drops numeric OS ownership/stat assertions, permission matrix, direct snapshot reading, additional directory/file registrations, extra selector wrappers and the redundant empty `call.View` setting. No EPERM skip is introduced.

The host-compatible tests do not replace successful filesystem integration coverage. Existing ContainerSuite tests already cover actual WithFile bytes, explicit/named/inherited ownership, path expansion and mounted-file overwrite (`TestWithFile`, `TestWithFileOwner`, `TestWithFileOnMountedFile`). The retained privileged proof covers the newly selected branch, mode, unchanged parent and capture/reopen followed by actual bytes. The parent's actual configured HTTP check is a separate runtime proof that the custom service base is still consumed. Do not claim new/restored failure tests prove all successful copy behavior by themselves.

Next authorized focused validation, outside any timed benchmark:

```
GOMAXPROCS=4 go test -mod=readonly -overlay=/tmp/collections-perf/sdk-edit-audit/withfile-source-lazy/upstream-v1/test-overlay.json ./core/schema -run '^TestContainerWithFileDefersSourceFailure$' -count=1
GOMAXPROCS=4 go test -race -mod=readonly -overlay=/tmp/collections-perf/sdk-edit-audit/withfile-source-lazy/upstream-v1/test-overlay.json ./core/schema -run '^(TestContainerWithFileDefersSourceFailure|TestBuiltinMetadataConsumersStopOnFailure)$' -count=1
```

Run the first command with `baseline-test-overlay.json` separately to retain the expected failure. Once applied to an isolated engine-dev source and given a runtime slot, the standard integration route is `dagger api call engine-dev test --pkg ./core/integration --run='TestContainer/(TestWithFile|TestWithFileOwner|TestWithFileOnMountedFile)$'`. These commands are plans, not additional completed validations.

## Interface reconciliation

`/tmp/collections-perf/sdk-edit-audit/interface-signatures/prototype.patch` applies cleanly and independently. It includes only `dagql/interfaces.go`, `dagql/server.go` and `dagql/interface_signatures_test.go`. All current baseline source hashes match its manifest exactly; the test file is absent in the checkout as expected. `review-manifest.json` records this check.

No withFile, Dang, TypeScript, generated SDK, schema ownership, persistent cache or experimental runtime dependency is required. Existing focused unit/race and paired microbenchmarks remain valid for those identical sources. It reduces repeated signature materialization within one locked reconciliation pass, retaining relation/GFP, view and declaration-order semantics. Permanent-only relationships allocate no memoizer. The remaining pair comparisons and fixed-point iteration are unchanged.

The parent's matched full-flow experiment reports lower allocation but no clear warm wall gain (expanded listing approximately 1.535 to 1.531 seconds). Commit rationale should be reduced redundant allocation under schema reconciliation, not a promised whole-command speedup. An independent commit can therefore carry this patch with those explicit results and test provenance; it does not need to wait for the withFile production decision.

The parent subsequently applied both minimal patches to the shared checkout. No new validation has run yet. `baseline-test-overlay.json` now explicitly replaces container.go with `container.baseline.go`, reconstructed from commit 74d8b418 and verified against the original source SHA. This avoids accidentally testing the applied candidate as the baseline. `validate-applied.py --output <new-directory>` records input hashes, exact commands, JSON logs and results. It demands the specific construction-time failure in both baseline subcases, then executes focused schema/DagQL unit and race tests directly against applied sources (no candidate source overlays). Its execution remains pending an exclusive test slot.

The first applied validation stopped on an invalid baseline fixture: the eager path resolves destination rootfs before demanding source. Added the real rootfs resolver registration to both the shared test and its draft; the original failed run is retained in applied-validation-v1. Production source was unchanged.

## Final applied validation

All five required outcomes passed in `applied-validation-v2/results.json`: the unchanged production baseline fails at withFile construction in both cases; candidate schema unit/race and DagQL interface unit/race checks pass directly on applied shared sources. No candidate production overlays were used. Each command verified the same production hashes before and after. `applied-validation-v1` remains an explicitly rejected fixture attempt, not a baseline result. The only correction was adding the real rootfs resolver registration needed by the eager baseline.

- baseline-expected-failure: expected exit 1, package elapsed 0.096 s; command including compilation 20.456 s.
- schema-unit: expected exit 0, package elapsed 0.069 s; command including compilation 19.703 s.
- schema-race: expected exit 0, package elapsed 1.2770000000000001 s; command including compilation 89.712 s.
- interfaces-unit: expected exit 0, package elapsed 0.042 s; command including compilation 23.912 s.
- interfaces-race: expected exit 0, package elapsed 1.205 s; command including compilation 42.462 s.

No new engine, Cloud or benchmark calls were performed by this validation. The full successful-copy privileged proof remains in the parent directory unchanged. The production and unit patch here now includes the tested fixture registration.
