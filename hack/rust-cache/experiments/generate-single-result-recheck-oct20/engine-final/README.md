# Final engine implementation for #14184

[PR #14184](https://github.com/dagger/dagger/pull/14184) now uses the engine implementation at `06001d48dbfe6f631d0de95d2db3d909c417e521`, based on October 20 main `35b97b7e55abd108f2d10255f709afc82f00175d`. The earlier CLI shortcut is removed. This directory supersedes the live-recipe-only prototype in `../engine-only`.

## Complete-command performance

| Generated output | Main | Engine fix | Reduction | Faster pairs |
| --- | ---: | ---: | ---: | ---: |
| 32 bytes | 0.403 s | 0.332 s | 17.5% | 6/6 |
| 64 MiB | 2.368 s | 1.262 s | 46.7% | 6/6 |

Both versions run the identical stock CLI and runtime image. Each size has two excluded priming pairs followed by six measured pairs in alternating order. Every command starts a fresh CLI, changes the generator source and output text, resets the destination outside timing, runs `dagger generate -y`, and waits for successful process exit including export and session cleanup. Engines are warm; engine startup and first-use latency are not measured. The binary is deterministic byte data, not a Rust or Cargo build.

All 32 commands, including priming, exit successfully and pass full binary SHA-256, changed text, deletion, untouched text and Git-metadata checks. Every candidate preserves the requested binary mode `0750`; main reconstructs it as `0777`. Engines have separate retained volumes, a four-CPU limit and `GOMAXPROCS=4`. Normal CLI telemetry uses the existing local OTLP receiver. No cache policy changes, forced GC, overlapping build/test/benchmark workload, or existing-engine reset is used. This is one host, not a claim of complete isolation from unrelated host activity.

Separate wcprof captures are excluded from timing. The main capture spends 0.938 s in `Changeset.withChangesets`, including 0.746 s in `Changeset.__mergeWithChangeset`; those durations overlap. With the fix, the outer API still runs its usual input filtering and takes 0.194 s, but the nested merge and its Git staging are absent. Both captures have zero dropped events and zero open operations. Existing path computation and export still execute.

## Correctness and scope

The change adds 31 production lines across two files. An empty receiving changeset can reuse its single input's snapshots, with root `.git` metadata excluded through the existing cached directory operation. The guard recognizes only the canonical empty-directory recipe, not every directory whose diff is empty. An unchanged receiver may still contain meaningful base files that must survive a merge.

Recognition reads existing metadata under the existing per-directory mutex. It does not scan, evaluate or download a snapshot, or add a cache or global lock. The saved recipe handles evaluated snapshots after cache reopen, pending imports and already-acquired imports. Unknown older representations conservatively use the general merge. Zero inputs, nonempty receivers and multiple-input conflict handling retain their existing paths. Content-identical non-executable permission-only changes remain outside the exported path contract.

The new integration test fails on main for both public APIs (`0750` becomes `0777`) and passes with the fix. It verifies binary/text contents, `0750` and `0600` file permissions, an empty `0700` directory, deletion, both root `.git` directories and worktree files, and meaningful unchanged receiver bases. Existing `TestWithChangesets`, `TestChangesetMerge` and `TestMergeKeepsDirectoriesARemovalEmpties` also pass on the final engine.

The focused schema tests pass with the race detector. The reopen test uses a real persistable API result, closes the isolated cache and reloads the snapshot manager; it confirms a restored evaluated snapshot still takes the correct path. The transfer test serializes an exported Changeset and imports it into an independent store. Different platform identities keep preparation of the fresh input from accidentally acquiring the imported receiver first. Both pending and acquired imports preserve `0750`; `Snapshot.Peek` verifies that the pending snapshot remains unacquired even after the merge.

An earlier live-recipe-only guard failed the privileged reopen regression by producing `0755` instead of `0750` (that test container has a different umask from the daemon). The final helper fixes that case. A test-setup check that used `HasPendingLazyEvaluation` after acquisition was replaced with `Snapshot.Peek`: the former includes armed callbacks, so it is not proof that a snapshot is uninstalled. Neither diagnostic is a final timing sample. The full integration suite and cold-engine latency are unmeasured.

## Reproduction and evidence

`benchmark.py` contains the complete Dang fixture and alternating timing driver; `start-engines.py` records isolated engine creation and identity; `check-api.py` runs the identical compiled integration test against both engines. These are local investigation scripts, not a portable benchmark package: they depend on the runtime image, built binaries and existing local OTLP wrapper recorded in the paths and identities. Run `python3 benchmark.py` for the timing cohort and `python3 benchmark.py --profile --sizes 67108864` for separate diagnostics after supplying those local prerequisites.

`identities.json`, `builds.json`, `engines.json` and `engine.patch` record exact source and binary identities. `samples.json`, `summary.json`, `logs/` and `benchmark-driver.log` retain complete timing evidence. `profiles/` and `profile-summary.json` retain the separate diagnostics. The API logs include the negative main control, positive final engine and existing merge controls. `persistence-race.log` and `core/` retain the final race-test result and exact tested sources. Production and tests were built sequentially using Go 1.26.6.

While testing, main advanced to `b00d83ea63f9b7be901744d3ded65247687361d2`, changing only `engine/server/session_cloud_telemetry_test.go`. This cohort and PR commit deliberately retain the tested main base `35b97b7e55`; no timings are attributed to the later commit. All engines, test containers and volumes from this and earlier work are retained.
