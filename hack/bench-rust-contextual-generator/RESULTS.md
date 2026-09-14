# Contextual generator inputs: measured tradeoffs

Proposed module-only optimization, not a finished official module or a native
Cargo comparison. Two independent opposite-order pairs on a tiny two-member
Rust workspace. All timings below are whole-process milliseconds with profiling
enabled; six samples per flow per arm. No listener or persistent CLI session.

Both arms use the already optimized contextual check entrypoints. The change
makes the generator's source and observed output state explicit Directory inputs,
so the normal function cache can reuse its complete Changeset across standalone
commands. Cargo settings, actual outputs, and host drift checks remain inputs.

| Flow | A/B before | A/B candidate | Saving | B/A before | B/A candidate | Saving |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| First default check after prior generation | 854.300 | 864.648 | -10.347 | 769.876 | 810.164 | -40.288 |
| Novel library edit + default check (reports artifact drift) | 2052.351 | 2037.907 | 14.444 | 2026.821 | 1983.495 | 43.326 |
| Generate after that check, including artifact export | 947.733 | 691.045 | 256.689 | 897.107 | 627.059 | 270.048 |
| Direct novel edit → generate, with no preceding check | 1340.199 | 1253.669 | 86.530 | 1365.983 | 1176.976 | 189.008 |
| First unchanged generate after direct generation | 911.810 | 884.735 | 27.075 | 977.928 | 823.553 | 154.375 |

Positive saving means faster. Raw samples, min/max and the median of individually
paired deltas are retained in evidence.json; the table subtracts arm medians.
No outliers were removed.

The repeatable strongest result is check → generate: approximately 257/270ms saved.
The generator field itself hits in all 12 candidate followups, while it executes
in all 12 baseline followups. Zero Cargo processes run in either followup arm;
artifacts are still exported and executed to verify changed behavior.

Direct edit → generate also improves in both pairs (87/189ms). Each sample
contains exactly one successful Cargo build action; no check prewarms it.
Median process wall minus that sole execution is 1064.452→969.522ms in A/B
and 1054.580→880.568ms in B/A. Thus the observed savings are not merely faster
Cargo execution in the candidate; this is still a small profiled workload.

## Limits and regressions

Cached-default medians regress by 10.347/40.288ms. This is **not** a general
cached-check improvement. Applying the Changeset changes outputState; the next
default check normally runs the generator once for that new source/output pair.
Subsequent identical state can hit. Novel default-check improvements are much
smaller than export improvements. First unchanged-generate gains vary widely.
One-off unlocked generation and alias/setup regressions remain in the raw CSV;
none is hidden by aggregating with the six-sample loops.

Cold first-check process times, including automatic engine provisioning:
r2 before 18.462s, r4 candidate 18.470s, r5 candidate 32.415s, r6 before 18.864s.
All four cold profiles fail the <=2% replay gate. The 32.415s run is retained,
not erased by faster runs. Its raw trace includes an approximately 19.37s HTTP GET;
the failed replay does not support a profiler what-if claim. No cold win.

Across the compared runs, all 268 ordinary command runtime assertions pass.
Of 264 warm command profiles, 263 pass all completeness/drop/structure/replay gates.
The initial Clippy command in r6 lacks its engine span-count carrier, so its
profile is rejected despite successful runtime assertions. Every sample in the
five six-sample timing groups above passes all wcprof quality gates. Full-run
acceptance remains false (cold replay and that Clippy capture); do not describe
this as an entirely accepted profiling suite or make a Clippy speedup claim.

## Correctness evidence

Both candidate runs exercise 75 commands each; before runs exercise the identical
first 59 commands. Sixteen additional candidate commands run only after that timed
prefix, exercising output-state correctness. Comparison tooling verifies the
prefix and all common engine/CLI/assets match.

Checks, fmt, Clippy, unit tests and builds actually execute on novel edits.
Source-only edits do not rerun toolchain preparation. Compile/manifest/config/
toolchain/settings failures propagate; repairs and older snapshots reuse correct
results. Locked and unlocked lockfiles, settings inheritance and installed alias
are checked. Default check reports generator drift without applying it; generate
applies outputs and the Linux binary's changed behavior is verified.

Additional probes cover deletion, obsolete outputs, executable-mode mutation,
missing/empty managed directories, nondefault target ancestor modes, unrelated
target siblings, and symlink rejection for target, target/dagger and unlocked
Cargo.lock. Outside sentinels remain unchanged. Deleted/modified outputs are
restored byte-for-byte and mode-for-mode without Cargo execution. Changing only
an unrelated target sibling preserves a generator hit and leaves the sibling
untouched.

An earlier self-call candidate is **rejected**, not in this change: it failed
under an installed alias and added approximately 155ms of native Dang work on a
representative direct-build miss. r1 also had a retained fixture quoting failure;
r3 corrected that test and exposed the alias failure. Their captures are retained
under the owner, but neither is an accepted before/after comparison.

## Provenance and scope

Owner: /tmp/dagger-rust-build-output.vrRYC6gW.
Pairs: r2-before versus r4-candidate (A/B); r6-before versus r5-candidate
(chronological order r5 then r6, B/A).
Before main.dang SHA256: f995374afcfda19442427e1160a12569064a340d2c1cbc5b4cd4a650460ed45a.
Candidate main.dang SHA256: 7e0d30cd3c058907fb858f22925a48fcec591d52860d021d04785a5d692a97d7.

Exact common engine/CLI provenance is retained in
[the shared engine receipt](../bench-rust-contextual-checks/engine-provenance.json).
Engine build is commit 0d28f80b plus the recorded singleton Changeset and GC-reserve
patches, identical in both arms. These separate engine changes are **not**
silently included in the module commit. Current main was re-fetched at 18c593d;
its only change since the tested ecd1ec21 base is eight lines in the docs 404 page.
No new runtime-code revision or rebuilt-engine claim is implied.

Root-invoked Linux/amd64 prototype only. Nested cwd behavior is an inherited
unresolved limitation: generators rebase under invocation cwd while this module
reads workspace-root inputs. macOS/remote, engine-restart/concurrent correctness,
full onboarding, pinned real-repo/native comparisons and actual external dependency
upgrade performance remain outstanding. The goal is still unmet.
