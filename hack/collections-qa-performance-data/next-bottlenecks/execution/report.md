# Execution benchmark matrix on Kyle's greetings-api

Executed 2026-09-25 on the complete experimental static-TypeScript/Dang engine with direct Cloud telemetry; the raw measured series is archived under `measured/`. These commands follow the current collection/check declarations rather than treating a listing as test execution. Source review uses greetings-api `14d684fccf75a137de96f3f0c7eb8c6dafef2d3e` and Go module `1784ff37eb3dd1aacab7aaff91b1d86e311cc8de`, pinned by the existing fixture lockfile.

The measured operation must remain a fresh CLI process with the complete configured workspace, telemetry, process exit, and Kyle's service-bearing Go base. Removing that base or invoking `go test` directly would measure a different user flow.

## Exact user commands

Run from the greetings-api workspace. Add the chosen `--engine container://NAME` before `check` when targeting a particular benchmark engine.

| Scenario | Command | Correct result |
| --- | --- | --- |
| One real unit test | `dagger check --generated=false go/modules/tests/run --go-module=. --go-test=TestFormatResponse` | Exit 0, one passing grouped Check; test selection contains only TestFormatResponse. |
| Two selected unit tests | `dagger check --generated=false go/modules/tests/run --go-module=. --go-test=TestSelectGreeting --go-test=TestFormatResponse` | Exit 0, one passing grouped Check replacing the two item checks; one module test invocation with a two-name anchored `-run` pattern. |
| All root tests, including HTTP e2e | `dagger check --generated=false go/modules/tests/run --go-module=.` | Exit 0, one passing grouped Check; all six root test names, including all four TestE2E functions. The complete collection branch uses `otelgotest ./...`, preserving examples as well. |
| Warm rerun | Repeat the exact command above from a fresh CLI | Same correct result; report cached result reuse separately from process/test execution. |
| Real source edit | Append a comment to main.go, immediately run the single-test command, then restore and rerun | Both succeed; unchanged discovery keys do not justify reusing the old source snapshot blindly. |
| Edit invalidation proof | Insert `t.Fatal("execution-perf-invalidation-sentinel")` at the start of TestFormatResponse, then run the single and two-test commands | Both fail nonzero and include the sentinel. Infrastructure failure alone does not satisfy this assertion. |
| Selection proof | While that failing test remains, run `dagger check --generated=false go/modules/tests/run --go-module=. --go-test=TestSelectGreeting` | Exit 0: the unselected failing test must not run. |
| Restore proof | Restore main_test.go and rerun the single-test command | Exit 0; failure must not remain cached across restored content. |

A one-time `-l --all` on each selection checks its exact keys before execution. Listing output should contain respectively one, two, or six rows at `dag+check://go/modules/tests/run`. It is a correctness preflight and is excluded from execution timing. Successful check output is rendered via telemetry; stdout is not a stable JSON result contract. The driver checks exit status plus one grouped Check in the final summary and preserves raw stdout/stderr.

**The historical `dagger check go/modules/test` command is not the current check surface in the pinned Go module.** GoModules.test and GoModule.test are ordinary methods; the `@check` directives now live on GoTests.run and GoTest.run. Benchmarking the historical path could measure an empty/invalid selection rather than tests.

## Distinguish four cache states

1. **Fresh engine cold execution:** new engine state/cache volume, exact image/module pins, same command, no discovery preflight. Measure separate replicas for each scenario; running single then pair on one engine does not give two cold samples. Record local registry/host caches and network state. A separate fresh-engine profile is needed; profiling cold and using that duration as an unprofiled baseline would mix boundaries.
2. **First execution after listing:** discovery/SDK caches may be warm, while scanner, runner, application build and actual tests have not run. The prepared driver labels this explicitly and does not call it cold.
3. **Warm rerun:** complete fresh CLI command on unchanged sources and retained engine. Dagger may reuse an execution result; Go may reuse a test result. Both are legitimate normal UX, but neither proves a fresh test process executed.
4. **Warm edit loop:** write the source change and immediately launch the command. The sentinel failure plus restore checks that invalidation is real. Profile a separate changed comment so it cannot merely replay an earlier edited snapshot.

The script starts/stops no engines and prunes no caches. The caller assigns an already-running engine exclusively. It copies the full fixture under its output directory, preserves the configured module/settings/lock inputs, changes only that copy, restores both edited files in finally, and verifies the original app's file hashes are untouched.

## Execution work that listing did not measure

- `GoModule.testEnv` asks the Go library to provide otelgotest, source includes and testdata.
- Kyle's base is `dag://backend/go-test-base`. Backend.GoTestBase binds Backend.Serve, which depends on compiling the API binary. That binding remains on every derived container, including `command -v otelgotest`. A unit test can therefore incur API build/start costs even without calling HTTP. The benchmark must retain that configuration to stay comparable.
- `gomod.scan` builds go-includes in its pinned Go image, imports the Go-source/go.mod snapshot, and runs `go-includes --all --output-dir /output --test`. The scan output is content-addressed and shared; listing intentionally bypasses it.
- The fallback runner is `go install github.com/dagger/otel-go/cmd/otelgotest@main` in the pinned tool-builder container. An existing custom otelgotest must remain respected. `@main` also means a fresh cold build can resolve a different runner revision; record the resolved runner provenance rather than attributing all cross-day variation to engine performance.
- A selected subset runs `otelgotest -run '^(...)$' ./...`; selecting the entire collection takes the module-wide path with no regex and includes examples. Four e2e tests depend on GREETINGS_API_URL and otherwise skip. Retaining the configured service is necessary, and their telemetry must show test execution rather than skipped outcomes before calling the full-suite correctness run successful.

## wcprof boundaries to capture

Use `dagger --profile ...` in separate captures after the unprofiled warm series, drain previous events first, and save `/debug/wcprof/dump?flush=true` after process exit. Require zero dropped events and investigate any open operations. The prepared driver can collect separate warm-single, warm-pair and edited-pair dumps; `--profile-first` additionally captures first execution after the listing preflight.

| Phase | Evidence to inspect | Question |
| --- | --- | --- |
| Selection/discovery | Workspace.artifacts, go:Go.modules, GoModule.tests, Workspace.search, findRoots | Does an explicitly selected test avoid unrelated SDK/module discovery? |
| Planning | Artifacts.__evaluationItems, new `artifact.batch`, collection projection/metadata calls | Does the two-key selection become one GoTests.run and one execution rather than two GoTest.run executions? |
| Module evaluation | dang.invoke/runSource/selfTypes, module runtime execs, Query.node/session.query | Are pure forwarding/path/schema operations crossing runtime boundaries unnecessarily? |
| Source preparation | gomod scan/source/testData, Host.directory, File.contents, snapshot/mount operations | How many whole-workspace scans and materializations happen, and which survive a small edit? |
| Tools | exec argv for go-includes build/run, `go install ...otelgotest@main`, `command -v otelgotest` | Are immutable helpers reused; is a tool probe starting a service or eagerly building an unused fallback? |
| Application service | Backend.build/binary/serve, go build, service.start/readiness | Is the service starting once; does a test-only edit force unrelated backend execution? |
| Tests | otelgotest argv, container-exec outcome, go/test telemetry and logs | Real process run, Dagger result hit, or Go test cache hit? Selected names and pass/fail/skip must agree. |
| Completion | CLI process wall time against final engine/test span | How much fixed export/shutdown cost remains after actual execution? |

Avoid summing overlapping spans or treating the analyzer's final-root what-if figure as whole-CLI savings. Report complete command time, execution/cache outcomes and phase evidence together.

## Further candidates grounded in source

1. **Backend input boundary:** Backend.New imports almost the entire repository (ignoring .git, node_modules and website); Backend.goBase mounts it all before go build. A test-file, README, frontend or unrelated SDK edit can therefore invalidate the backend execution recipe although the Go binary may not depend on that content. A source-aware build mount could reduce re-execution, but must preserve go:embed, local replacements, generated inputs and cgo files. Prove that narrower source contract before changing this benchmark's baseline.
2. **Tool probing and eager arguments:** `gomod.withTool` probes PATH using a container exec and receives its fallback binary as a File argument. Profile whether obtaining that argument causes an unnecessary build when a custom tool is present and whether the probe triggers service startup. A lazy fallback must preserve user-supplied tools and normal DagQL dependencies; a blanket cached “tool exists” flag is unsafe across image/PATH/workdir changes.
3. **Batch schema work:** the new key index fixes membership complexity, but CollectionBatchType still reconstructs the same metadata for each selected item and Child enumerates all child fields just to select one. Request-local memoization keyed by module/server and object type could remove redundant work without persisting user selection state. Two or six tests are too small to credit the 10,000-key microbenchmark gain to this fixture.
4. **Execution source scan granularity:** the shared all-workspace scan is excellent for many modules, but a single-module test still rescans all Go-source/go.mod input after any such edit. Per-module scan nodes with explicit local-replacement/directive dependency edges could reuse unaffected modules while retaining content-addressed correctness. Validate this on a real larger workspace before accepting added complexity.
5. **Names-only findRoots:** current descendantRoots imports marker file bytes and creates/mounts a Directory before globbing filenames. A narrow host fast path can reuse FilesyncSource's NewFS + NewFilterFS with identical Include/Exclude/FollowPaths, return names/stats through the existing authenticated client channel, and retain the existing fallback for overlays/mounts/engine-backed workspaces. Keep `PerClientInput`; do not cache host filenames by path/TTL. Multiple markers should share one enumeration. The source audit must cover root symlinks, CopyFilter pruning, marker grouping/order and newline/unusual filenames. Plain Workspace.glob is not an equivalent replacement. Current measured aggregate findRoots work is only ~47–50 ms for seven calls; no larger saving is claimed.

## Prepared driver

`benchmark.py` defaults to printing its plan and makes no engine call until `--run` is supplied. Example after an exclusive slot is assigned:

```sh
python3 /tmp/collections-perf/warm-audit/execution-matrix/benchmark.py \
  --engine ENGINE_NAME \
  --cli /tmp/collections-perf/rebase-main/dagger \
  --output /tmp/collections-perf/execution-first \
  --profile-port DEBUG_PORT \
  --run
```

Add `--include-full-module` for the six-test HTTP-enabled case. The initial real execution will build any missing application/tools and may take much longer than listing. First execution, warmups, eight warm repetitions per selection, real edits, negative/positive controls and separate profiles are labeled independently. **The full matrix completed successfully, including the HTTP-enabled six-test case, selected failure propagation, unselected passing control and source restoration.**


## Recorded baseline and measured follow-up

The CLI/engine/fixture hashes are recorded in `measured/provenance.json` and the
static-TypeScript experiment's engine manifest. First execution below follows
listing preflights on a retained engine and must not be labeled fresh-volume cold.

| Case | Complete CLI time |
| --- | ---: |
| First single-test execution after discovery | 40.075 s |
| Warm single selected test, eight-run median | 2.150 s |
| Warm two-test batch, eight-run median | 2.144 s |
| Warm all six tests, eight-run median | 2.130 s |
| Fresh application main.go comment then single check | 11.778 s |
| Restore application source | 2.350 s |
| Insert selected test failure | 11.261 s, expected nonzero exit |
| Unselected passing test with failure still present | 2.665 s |
| Batch containing failing test | 2.561 s, expected nonzero exit |
| Restore test source | 2.347 s |

A separate edited-pair wcprof capture shows the backend's actual `go build`
process taking 8.150 s, with the selected test-runner process taking 411 ms.
The backend builder has neither Go compiler nor download cache mounts. Warm
captures contain no new build, scanner or test-runner execution: they correctly
reuse previous Dagger results.

The subsequent [backend cache experiment](../backend-go-cache/report.md) adds
normal cache mounts to the actual builder and repeats five unique application
edits, alternating the original and patched module. That validated comparison
improves **11.446 → 3.559 s**. The two-test command and series differ from the
single original edited observation above, so use its matched baseline rather
than subtracting the two unrelated measurements. Both variants fail after a
changed API response and pass all six tests after restoration.
