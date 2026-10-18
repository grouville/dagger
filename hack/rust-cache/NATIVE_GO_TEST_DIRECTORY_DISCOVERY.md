# Derive package test directories from one native snapshot

Complete Go test listing after a test-file edit improves **12.22 → 11.25 seconds median**, faster in all four balanced pairs. Ordinary-source edits are essentially unchanged at **6.01 → 5.98 seconds**, faster in two pairs. These are warm-engine measurements with fresh CLI processes, telemetry, ordinary GC, cleanup and final log flushing included. This change's cold-start effect is not measured.

| Warm edited listing | Before | Candidate |
| --- | ---: | ---: |
| Test-file edit, complete command | 12.22 s | 11.25 s |
| Test-file edit, engine CPU | 68.92 CPU-s | 59.24 CPU-s |
| Test-file edit, cumulative allocation | 16.56 GB | 15.43 GB |
| Ordinary-source edit, complete command | 6.01 s | 5.98 s |
| Ordinary-source edit, engine CPU | 25.40 CPU-s | 25.65 CPU-s |
| Ordinary-source edit, cumulative allocation | 6.30 GB | 6.26 GB |

The command is `dagger check --module go --check test --list --all` on dagger/dagger `ff0b029a4d270a651b9a8c7286babc79089066e4`. Every invocation edits ordinary Go source; the test-edit cohort also edits a test-file comment. Two excluded initialization blocks add and then remove a real test in both arms before four measured pairs. All 24 commands exit successfully with identical expected ordered names and complete row text: 4,399 during addition and 4,398 afterward. No profiler, build or other test runs alongside timings. The test-edit median paired saving is 0.98 seconds; CPU and allocation are lower in every pair. Host CPU pressure peaks at 25.2% and I/O pressure at 0.18%. Allocation is cumulative work, not peak resident memory.

## Change and correctness

The module already prepares a native immutable snapshot of test files. Previously each of 800 package getters asked whether its directory existed in that snapshot. Discovery now walks the snapshot once and carries the directories containing direct `_test.go` files into the collection. Getters check that list before taking the same per-package native directory view. A parent containing only descendants' tests gets an empty view, as its direct test-file filter did before.

This changes about 22 production lines in `go.dang`, without an engine change, dependency, lock or separate cache. Files and directory information come from the same snapshot. An absent list retains the previous existence-check fallback. Membership is linear in the directory count, which is 103 here; larger counts need a scaling check.

Seven focused commands pass, including the new fixture on both baseline and candidate. The fixture covers root and child tests, parents with only descendant tests, absent directories, empty test files, literal and Unicode paths, nested modules, source overrides, added and removed files, changed working directories and execution of a default-snapshot test. Existing discovery, layout rebind, collection execution, binary and generation checks pass. Source, configuration and temporary switches are restored.

## Profile and limits

Separate lossless wcprof captures confirm **800 → 0 `Directory.exists` calls**, one extra `Directory.glob` and **164 → 94** native subdirectory calls. SDK requests fall **2,293 → 1,494**. Evaluations remain **804**, with 800 getters executed and 799 unchanged test discoveries reused.

The diagnostic candidate runs slower: **14.02 versus 13.02 seconds** for the complete profiled command, **13.49 versus 12.49 seconds** for its main query. These single captures establish operation counts; the unprofiled balanced pairs establish the latency gain. Getter preparation still decodes 81.4 MB of parent JSON versus 79.6 MB before because every receiver carries the new list. Reducing those 800 preparations and shared root discovery remains necessary for the three-second target.

Candidate `grouville/go:experiment/snapshot-test-directories`, commit `a3d0e4bf562b834c31135bff24e5931fd32b3acc`, has parent `09518aac0858390722e71c82a719c2f6e131e611`. Both arms use engine SHA-256 `37d4c555e4c5bf4370f7aa70b653a53b576ba08fa9c615898bb03bff6b8eb122` and CLI `97f7d82dc2f7b3da203aa683971ea3658b6de6a8e9b968a44905e379f499f965`, with selected metadata, projection, getter identity and both Dang fixes common. Shared function metadata, marker sharing and experimental sorting stay excluded. No engine restart or binary replacement occurs; the original Rust engine is unchanged.

Retain this small module follow-up. Its parent still contains the experimental snapshot discovery API; a compatible standalone port and broader upstream checks remain before opening a PR. No PR is open. [Review description](PR_GO_TEST_DIRECTORY_DISCOVERY.md), [evidence](experiments/go-snapshot-test-directories/), [separate cold results](NATIVE_GO_COLD_LISTING.md).
