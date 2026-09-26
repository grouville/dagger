# Constructor-only caching: work removed, no established wall-time improvement

The generated-metadata candidate correctly removes one Go runtime invocation
on unchanged source. This experiment does **not** establish faster overall
listing or edit-to-check time, and does not justify upstreaming a module-wide
cache-default change for a claimed speedup. No shared source or public module
was modified.

## What was changed and validated

The Backend constructor only stores its explicit Directory input. Both
isolated variants add `+cache="session"` to Build, Binary, Container, Serve and
GoTestBase. The control keeps disableDefaultFunctionCaching=true; the candidate
sets it false. Thus only the pure constructor gains ordinary cross-session
reuse. This uses existing caching behavior, not a new engine cache mechanism.
Both sides already include the separately validated compiler cache mounts.

Normal pinned Go SDK generation ran on both variants. Emitted metadata has
exactly five PER_SESSION registrations, default New, preserved defaultPath,
ignore patterns, Serve's up marker, and current source maps. The generated
registration SHA is identical on both sides:
`d743ffe9c3171ada94715042d127efd3b2d890c202951d0936a5f97e963038ec`.
After generation, recursive comparison finds only the intended backend config
flag differs between the two complete workspaces.

The first attempt to generate every Go scope correctly failed the experimental
TypeScript metadata freshness guard while loading greetings' frontend
dependency. No changes were applied. The successful normal generation
temporarily selected only the backend SDK scope, then restored the original
dagger.toml byte-for-byte. No backend callable signatures changed, so greetings'
dependent client signatures did not need regeneration. This setup workaround
did not bypass or re-seal the TypeScript guard.

The full generated patch is `constructor-with-generated-metadata.patch`, based
on the earlier compiler-cache candidate. Normal SDK generation also refreshes
backend/internal/dagger/dagger.gen.go (+649/-15 lines of current core API,
including AgentMiddleware). This common regeneration is present in both
measured variants; it is not itself the constructor-policy change. The patch
was not reduced by hand-editing generated output.

## Complete CLI measurements

Every sample uses a new CLI process, retained engine2, normal direct Cloud
telemetry, and process exit as its endpoint. The engine is the existing
experimental TS-static/Dang stack, not an untouched collections branch. The
CLI is `/tmp/collections-perf/rebase-main/dagger`, SHA
`aea19ce8b7849905113c388b353b6a686aca6a55fbb0fe714f406a5bb8d2356d`.
No competing builds or engine workloads ran during the series.

After two warmups per command kind/variant, five matched pairs reverse order
on alternate iterations. Profiles are separate from measured timings.

| Five-pair median | Control | Constructor candidate |
| --- | ---: | ---: |
| `dagger check -l --all` | 3.273 s | 3.468 s |
| Fresh comment edit then selected paired check | 3.675 s | 3.487 s |

Listing favors the candidate in only 2/5 pairs; the median paired difference
is **+98 ms**. No listing wall-time improvement is established.

The edit result favors the candidate in 4/5 pairs, but is not an isolated
constructor saving. Each iteration uses fresh main.go bytes, with **identical
bytes within its matched pair**. Common lower-level content results can be
reused by the second variant. With five pairs, control runs first three times
and candidate twice. Exact filenames, content hashes, order and raw times are
in `measurement/paired-order-and-source-hashes.json`. A fresh source edit does
not imply every lower cache layer is cold; that would also misrepresent a
normal dev loop.

The separate edit profile is control first, candidate second, main.go SHA
`83e4d2542c45ac3c581fa291811f42e9ec6ddb3628932c6706f1bb75153e8db7`
on both sides. Control executes go-includes for 120 ms; candidate does not
execute it. Both constructors execute after the edit (91/95 ms), as required
for current source. Therefore the observed edit wall difference must not be
attributed to constructor caching. Even unique comments on each variant would
not guarantee unique downstream outputs: a parser may produce the same
discovery result. A future isolation run should retain those cache facts.

## Before actual check execution

These are individual diagnostic captures, not medians. CLI start/exit wall
timestamps are aligned with wcprof's same-host epoch; no wall-clock step is
assumed. All six captures have zero dropped events and zero open operations.

| Profile boundary | Control | Candidate |
| --- | ---: | ---: |
| Warm: CLI start to selected Check producer | 1.504 s | 1.366 s |
| Warm: CLI start to Check.sync | 1.504 s | 1.367 s |
| Edited: CLI start to selected Check producer | 1.844 s | 1.954 s |
| Edited: CLI start to Check.sync | 1.844 s | 1.955 s |
| Edited: CLI start to actual otelgotest process | 2.489 s | 2.375 s |
| Edited: actual otelgotest process duration | 415 ms | 376 ms |
| Edited: Check.sync completion to CLI exit | 584 ms | 471 ms |

The selected producer is `go:GoTests_Batch.run`; it returns a Check. Check.sync
evaluates it, and exec.processRun with otelgotest argv marks actual test process
execution. Artifacts.__evaluationItems is discovery/planning, not check
execution. Warm checks reuse earlier results and have **no fresh test process**.
Do not describe them as rerunning the tests.

On warm source, the Backend constructor changes from an executed 91–96 ms
call to a roughly 0.04 ms cache hit. GoTestBase still executes once per fresh
session (94–102 ms), preserving its policy. After edits, both constructors and
GoTestBase execute; the latter includes the nested API build (~398/376 ms).
Nested build/runtime durations are not additive savings. The residual tail
includes RPC/output/shutdown work and has not been wholly attributed to Cloud.

## Historical listing baseline cross-check

The historical static-TS listing and earlier CLI-baseline listing already
contained **six** Go runtime processes: four ModuleSource.asModule registration
processes, Backend constructor, and GoTestBase. Regenerated control still has
six; candidate has five. The earlier three-versus-two runtime counts describe
the selected-check path, not full listing. No extra registration process was
introduced by generation.

Recorded engine spans are historical static 1.418 s, previous CLI baseline
1.290 s, regenerated control 1.352 s, candidate 1.251 s. The current listing
CLI's 3–4 s total is therefore not explained by new runtime processes. Much of
the difference is outside recorded engine work; its cause remains unproven.
`runtime-ancestry-comparison.json` preserves the four matching profiles and
their call ancestry. Four registration durations must not simply be summed
as removable wall time, because some execute concurrently.

## Correctness and remaining scope

All listings match the exact 14-row expected stdout SHA
`c5ab5a8e1e456367b3c15e934d3d6fd7d62b315967d8d7c9571a24b2bbde63d6`.
Selected actual checks pass. Changing the compiled API response to contain
constructor-cache-api-sentinel makes the HTTP check fail in both variants.
Restoring behavior with fresh source runs **all six tests, zero skipped** in
both variants. All original tracked fixture hashes are unchanged; measured
configs, lockfiles and generated metadata are unchanged; copied main.go files
are restored. Engine2 was handed back running and idle.

The independent Go/TypeScript/Dang marker fixtures are **prepared only**. Their
cross-client, same-session, explicit Directory, nested-cwd and overlay cases
were not executed, so this report does not claim those additional proofs.
Ordinary caching already exists across SDKs. This module-specific migration
does not make it automatic for legacy opt-outs, and the measured wall results
do not yet support recommending that migration as a performance improvement.
