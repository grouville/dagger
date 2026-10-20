# Does the optimization still help inside the engine?

This is the initial live-recipe-only experiment. The [final engine implementation](../engine-final/README.md) supersedes it with cache reopen/import support, final tests and a fresh standalone comparison.

Yes. A direct comparison on the same October 20 main base (`42795401a9`) shows a 40% reduction for the 64 MiB output, with the CLI unchanged.

| Complete `dagger generate -y` | Main | CLI optimization | Engine optimization |
| --- | ---: | ---: | ---: |
| 32-byte output | 0.636 s | 0.489 s | 0.514 s |
| 64 MiB output | 2.166 s | 1.110 s | 1.291 s |

For the large output, the engine wins in all six comparisons against main, saving about 0.87 seconds by the medians. The small control improves 19% and wins in five of six comparisons. The CLI version improves 49% for the large output. Use this three-way cohort to compare the approaches; do not subtract numbers from the earlier separate cohort.

All 48 commands, including priming, have successful exits and correct content checks. The engines are warm; every command starts a fresh CLI and edits the source and output text. Timing includes export and session cleanup, but excludes resetting and checking the fixture. Each arm has a separate fresh volume, the same runtime image, a four-CPU limit and normal telemetry. Two priming triplets are excluded, then six triplets alternate forward and reverse order. No build, test or other benchmark from this task overlaps the timing cohort.

The production patch adds 19 lines to `core/schema/directory.go`. It recognizes a receiving changeset whose before and after directories both come from the empty-directory operation. It then uses the incoming snapshots, excluding root `.git` metadata as the existing merge does. Other receivers retain the existing Git merge path. Both `withChangeset` and `withChangesets` benefit. No CLI change, extra cache, retained index or new lock is involved.

## Why it is slightly slower than the CLI version

Separate wcprof captures show that the engine version eliminates `Changeset.__mergeWithChangeset`, just like the CLI version. The ordinary `Changeset.withChangesets` API call remains and takes 188 ms in the engine capture. Its snapshot-exclusion calls total less than 1 ms. Before reaching that shortcut, this API still runs its existing empty-input filtering and path computation.

That retained analysis is consistent with the approximately 181 ms difference between the CLI and engine medians. This is not 181 ms of new guard or locking overhead. The CLI shortcut skips that initial API analysis. All three captures have zero dropped events and zero open operations; profiled runs are excluded from the timing medians. Path fields share work, so their overlapping durations must not be added.

## Correctness

The same new integration test binary runs against stock and modified engines with the stock CLI:

- On main, the permission regression fails for both APIs: a requested `0750` becomes `0777`.
- On the engine candidate, both API cases pass, including binary/text contents, `0750`/`0600` permissions, an empty directory, deletion and exclusion of root Git metadata from both snapshots.
- An unchanged receiver containing a meaningful base file retains that file on both engines. Testing only whether a changeset's diff is empty would not be a safe guard.

Existing `TestChangesetMerge`, `TestWithChangesets` and `TestMergeKeepsDirectoriesARemovalEmpties` also pass on the candidate, including nonempty receivers, multiple inputs, empty inputs and conflicts. Tests run with `-test.parallel=1`, separately from timing.

This remains a local engine prototype. Its guard recognizes the live empty-directory operation. Recognition of an evaluated directory restored from a persisted snapshot has not been validated; those values use a different lazy wrapper and can fall back to the old merge. That needs addressing before presenting this as a complete replacement for #14184. Cold-engine latency and the full integration suite are also unmeasured. No PR or public branch was changed for this experiment.

## Evidence

- `engine.patch`, `changeset_single_snapshot_test.go`: production change and focused regression.
- `identities.json`: same CLI hash for main/engine; same engine hash for main/CLI; exact source and test binary hashes.
- `samples.json`, `summary.json`, `logs/`: complete unprofiled commands.
- `profiles/`, `profile-summary.json`: separate wcprof observations.
- `api-results.json`, `api-main.log`, `api-engine.log`, `api-existing-merges-result.json`, `api-existing-merges.log`: negative and positive correctness controls.
- `benchmark.py`, `start-engines.py`, `check-api.py`: local harness, using the same local OTLP wrapper as the parent experiment.

The first setup attempt copied a symlink instead of the binary and exited before any workload. The harness was corrected to resolve binary paths; that failed container was retained. Only the healthy `dagger-generate-core-{main,cli,engine}-oct20-r2` engines appear in the measurements. All previous engines and volumes are retained.
