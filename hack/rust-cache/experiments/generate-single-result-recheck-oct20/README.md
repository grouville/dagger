# Recheck of the single-generator optimization, October 20

The performance benefit is still real on current main. Vito's suggestion to put the optimization in the engine is also sound: every API caller should benefit when an empty changeset receives one result.

The user subsequently authorized replacing #14184 with the engine implementation. The [final engine implementation and fresh measurements](engine-final/README.md) now supersede the CLI-only review and initial prototype below. The same PR branch now contains the engine change and regression tests.

## What Vito asked

[PR #14184](https://github.com/dagger/dagger/pull/14184) avoids merging one generator result through Git. It instead keeps the result's before/after snapshots, removes root `.git` metadata from both, and follows the existing verification/export path.

[Vito's October 2 review](https://github.com/dagger/dagger/pull/14184#pullrequestreview-5394388848) asks whether `dag.Changeset().WithChangesets([x])` could do this in core, and whether excluding `.git` explains the performance gain.

Since that review, [#14576](https://github.com/dagger/dagger/pull/14576), merged October 9, reduced the work done by changeset merges and expanded native workspace merging. Those improvements are included in this comparison. They do not eliminate the single-result Git merge used by `generate`.

On main `42795401a9285410d03c8fce23ae9d6f7cffd61f`, `core/schema/directory.go:1612` still filters the inputs and delegates a single result to `changesetWithChangeset`. That records `__mergeWithChangeset`; `core/changeset.go:1462` still materializes the changes and performs the Git merge. The native workspace merge applies to a different operation.

## Complete-command measurements

Both arms use the same engine binary built from main. The candidate CLI uses only the PR's production logic, adapted to the current generated Go API types. The source checkout remains clean; `candidate-cli.patch` is supplied through a Go build overlay. This excludes every unrelated optimization from the collections experiments.

The tested base is October 20 main `42795401a9`. During the review, main advanced four commits to `35b97b7e55`: a healthcheck-test adjustment and removal of unused internal BuildKit plumbing. Neither changes the generator or changeset merge implementation. The timings below belong to the tested base, not a rerun of those four commits; `main-advanced-during-review.json` records the comparison.

| Generated binary size | Main median | PR median | Reduction | Faster pairs |
| --- | ---: | ---: | ---: | ---: |
| 32 bytes | 0.436 s | 0.343 s | 21.3% | 6/6 |
| 64 MiB | 2.349 s | 1.236 s | 47.4% | 6/6 |

The median paired saving for the large output is 1.109 s. Measured ranges are 2.034–2.817 s on main and 1.190–1.757 s for the PR. This is a controlled large-output fixture, not a claim that all generators become 47% faster.

Each size has six alternating pairs after two excluded priming pairs. Each command starts a fresh CLI, edits the generator source, resets the destination, runs `dagger generate -y`, and waits for successful CLI exit, including session cleanup. Reset and output validation are outside the clock. Timed waits block on process exit rather than polling in 50 ms increments. Engines are warm; engine startup and first-use costs are excluded.

Engines have separate retained volumes, identical runtime assets and stock engine binaries, four CPUs each, and `GOMAXPROCS=4`. Normal CLI telemetry exports to the existing local OTLP receiver. No cache policy overrides, forced GC or simultaneous benchmark/build jobs were used. This is one host, with no claim of complete isolation from other host activity.

All 32 commands, including priming, completed successfully. Each checked the output's complete SHA-256, changed text, deletion, untouched text and unchanged Git metadata. The binary is deterministic byte data; it is not a compiled Rust application or a Cargo build benchmark.

An earlier exploratory cohort used `subprocess.run(timeout=...)`, whose process wait can add up to 50 ms of polling delay. Its medians were 2.070→1.142 s and 0.465→0.365 s. It is excluded from the table; the final cohort uses a blocking wait. It remains under `/tmp/generate-14184-review/polling-timer-preliminary` for provenance.

## Where the saving comes from

Separate wcprof captures, excluded from timing results, show:

| Operation, 64 MiB case | Main | PR |
| --- | ---: | ---: |
| `Changeset.withChangesets` | 0.910 s | absent |
| Nested `Changeset.__mergeWithChangeset` | 0.720 s | absent |
| Git staging of the generated output | 0.392 s | absent |

These durations overlap; do not add them. Both captures have zero dropped events and zero open operations. The before/after path comparisons and export still run.

This supports avoiding the merge as the source of the saving. Both implementations already exclude root Git metadata, and the fixture's Git directory is small. The CLI exclusion preserves the old merge's behavior; it is not a new optimization for copying a large Git directory.

## Correctness and changes since the original PR

A separate diagnostic reproduces the PR's permission test using freshly created private files copied into the output:

| Output | Requested | Main | PR |
| --- | ---: | ---: | ---: |
| Added binary | `0750` | `0777` | `0750` |
| Modified text copied from a private file | `0600` | `0666` | `0600` |
| Empty directory | `0700` | `0700` | `0700` |
| Untouched file | `0664` | `0664` | `0664` |

The permission problem therefore remains. Empty directories now survive on both arms; the old description should stop claiming that this PR is needed to preserve them on current main. The general merge's `applyContent` now explicitly recreates empty added directories.

As before, a content-identical permission-only edit is not an exported path and stays `0644`. The timed fixture uses `withNewFile` on an existing text file, which retains its existing permissions; the separate `--private-source` case tests the original PR's copy semantics instead. This is why its text-mode assertion differs from the timing samples.

These checks run through the real CLI and export path. The full integration suite was not rerun for this review, and no claim is made about multi-generator performance, cold engines or every Git metadata case on current main.

## Recommendation

Keep the optimization, but move it to the Changeset API and leave the CLI using the ordinary merge call. Retain a focused regression for snapshots and permissions at that API boundary.

The fast path must check the receiver too. One input does not imply that there is nothing to merge: the receiving changeset can have changes of its own, or a meaningful unchanged base containing other files. Returning the input just because `len(changes) == 1` would discard those. Preserve existing zero-input, conflict and Git-metadata behavior as well.

A subsequent [engine-only experiment](engine-only/README.md) now implements and measures a local prototype: the large-output command improves 2.166→1.291 s (40%) with an unchanged CLI, versus 1.110 s for the CLI shortcut in the same three-way cohort. Focused negative/positive regressions and existing merge tests pass as documented there. That initial prototype has now been replaced by the [final implementation](engine-final/README.md), which recognizes persisted and transferred scratch recipes and passes cache reopen and import regressions.

## Evidence

- `summary.json`, `samples.json`, `logs/`: final unprofiled comparisons and command output.
- `profile-summary.json`, `profiles/`: separate 64 MiB wcprof observations.
- `profile-samples-private-source.json`, `profiles-private-source/`: the original permission regression through the CLI.
- `identities.json`, `engines.json`, `candidate-cli.patch`: exact source, binary and container identities.
- `benchmark.py`, `start-engines.py`: local reproduction harness. It uses the local OTLP wrapper at `/tmp/rust-cache-sipsma-review/local_cli_collector.py` and the existing base runtime image recorded in `engines.json`; it is not a portable benchmark tool.
- `pr.json`, `reviews.json`, `files.json`, `commits.json`, `pr-14576.json`: public review and source-history snapshots.

The original clean checkout and built binaries are retained under `/tmp/generate-14184-review`. All engines and volumes from the broader performance work are retained too.
