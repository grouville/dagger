# Actual edit-to-check: backend compiler cache result

Measured 2026-09-25. **Five real source edits followed by the ordinary paired check improve from 11.446 s to 3.559 s median (68.9% lower).** Every pair improves. This fixes a module recipe issue using normal Dagger cache volumes; it is not a universal engine speedup or a 500 ms result.

| Case | Original backend | Backend with Go caches | Meaning |
| --- | ---: | ---: | --- |
| No-change warm, 5 repetitions | 2.242 s | 2.226 s | Effectively unchanged; existing Dagger results already reusable |
| Fresh main.go comment then check, 5 unique edits | 11.446 s | 3.559 s | 7.887 s less, 68.9% lower |
| Edit range | 11.351–11.736 s | 3.353–3.671 s | All five pairs favor cache mounts |
| Candidate first invocation with empty dedicated caches | — | 13.554 s | Retained engine, new cache fill and changed backend module; not fresh-engine cold startup |

The first control invocation was 3.229 s using the existing retained engine state. It is not a cold comparison with the candidate's fresh cache fill. No fresh-engine cold-start gain is claimed.

## Exact user flow and provenance

Each timed process runs:

```sh
dagger --engine container://dagger-engine.collections-disk-abba-2   check --generated=false go/modules/tests/run --go-module=.   --go-test=TestSelectGreeting --go-test=TestFormatResponse
```

The source is the preserved execution fixture copied from Kyle's greetings-api workspace. dagger.lock pins dagger/go@collections to `1784ff37eb3dd1aacab7aaff91b1d86e311cc8de`. The CLI is `/tmp/collections-perf/rebase-main/dagger`, SHA-256 `aea19ce8b7849905113c388b353b6a686aca6a55fbb0fe714f406a5bb8d2356d`. The retained engine is the previously recorded complete experimental static-TypeScript/Dang engine. This experiment measures a module patch on that common engine; it does not compare against Kyle's machine or an unmodified collections engine.

Normal direct Cloud telemetry and configured API service remain enabled. Each sample includes a fresh CLI process through exit. Two warmup pairs precede five alternating no-change pairs and five alternating fresh comment-edit pairs. Both variants receive identical application edits; the candidate differs only by four cache-mount/environment lines in the backend module. Profiles are separate from timing samples. No unrelated build or engine workload overlaps the measurements.

## What changed

`Backend.goBase` originally starts from golang:1.26-alpine, copies the full source, and builds the binary with neither a compiler cache volume nor a download cache volume. A source comment changes the source-backed exec input, so a new build runs. Cache files in a previous exec's output filesystem do not become input to that new build.

`cache-mounts.patch` adds the standard Dagger/Go recipe used by `dagger/go/gomod.withGoCaches` at the pinned revision:

```go
WithMountedCache("/go/pkg/mod", dag.CacheVolume("backend-edit-20260925-go-mod")).
WithEnvVariable("GOMODCACHE", "/go/pkg/mod").
WithMountedCache("/root/.cache/go-build", dag.CacheVolume("backend-edit-20260925-go-build")).
WithEnvVariable("GOCACHE", "/root/.cache/go-build").
```

The experiment uses fresh task-specific cache names, stable across edits, so initial fill is visible. An upstream patch can use ordinary module-local `go-mod` and `go-build` names. It should not key cache volumes by source revision. Go indexes compiled outputs by its compiler/toolchain/build inputs. Dagger still invalidates and executes the build when source changes; the compiler reuses valid work internally.

The official Go module already has these caches on its own containers. They are separate containers and module-scoped cache volumes; those mounts do not automatically apply to the app's Backend.goBase. The patch changes no image, source projection, build argv, service binding, SDK dependency or test selection. It narrows no inputs and bypasses no checks.

## wcprof confirms where the time went

The separate edited captures have zero dropped events:

| Observed process/span | Original | Cache mounts |
| --- | ---: | ---: |
| `go build -o greetings-api .` actual process | 8,216.9 ms | 407.0 ms |
| Backend.goTestBase enclosing call | 8,373.2 ms | 540.2 ms |
| `go-includes --all --output-dir /output --test` | 140.7 ms | 130.2 ms |
| Actual paired otelgotest process | 428.9 ms | 379.9 ms |

The backend call encloses the build: these two rows overlap and must not be added. The source and profile establish the missing cache mounts and expensive rebuilding. No Go `-x` package-compilation log was captured, so the report does not assign every saved millisecond specifically to standard-library compilation; downloads and linking can contribute too.

Warm profiles from the prior execution matrix contain the three Go SDK `/runtime` calls but no new go build, scanner or otelgotest process. Warm checks legitimately reuse Dagger results; they are not newly executed tests. The edited profiles above execute the build, scanner and actual two-test runner.

## Correctness after invalidation

For both variants, the experiment changes the compiled API's FormatResponse to append `backend-cache-api-sentinel`, then runs only TestE2EGreetingByLanguage. Both commands fail with that sentinel observed through the HTTP response. This proves the running service binary changes; the candidate is not serving a stale build.

Restoring the original behavior with another distinct source comment then runs the full module. Both variants report **six passed**, including all four HTTP E2E tests, with zero skipped tests. The candidate restore/full check takes 3.642 s versus 11.440 s for control; these are correctness observations, not part of the five-pair timing median.

The original main.go, main_test.go, e2e_test.go, dagger.toml, dagger.lock and backend main.go hashes are unchanged. Edited main.go in both copied workspaces is restored in finally. Candidate cache mounts remain only in the isolated candidate copy. The benchmark exited successfully; the retained engine was handed back running and idle to the parent.

## Upstream scope and remaining work

This small module patch uses Dagger's intended caching primitives and is suitable for upstreaming to the greetings-api backend recipe. The generic lesson applies across SDKs: immutable exec caching avoids identical executions, while language/compiler cache volumes reuse valid work inside executions after source invalidation. Audit the actual container running the compiler; caches mounted on a sibling toolchain container do not help it.

A truly empty cache still needs its initial build. This result does not replace distributed caching policy or claim that a fresh source edit can reuse an old final executable. The remaining ~3.56 s includes a real rebuild, real tests, module/runtime work, service startup and shutdown/telemetry boundaries. Those remain separate optimization targets.

An independent warm lead is the fixture's explicit `disableDefaultFunctionCaching=true`: the existing warm profile spends ~84 ms each in backend schema/runtime registration, constructor, and GoTestBase. The latter two use per-session caching under that flag. Opting deterministic functions into ordinary caching needs its own source-edit and policy audit; it was not changed in this experiment.

## Evidence

- `cache-mounts.patch`, `main.before.go`, `main.after.go`: exact isolated source change.
- `benchmark.py`: reproducible driver (dry-run by default).
- `measured/manifest.json`, `provenance.json`: source, CLI and cache identities.
- `measured/results.json`, `summary.json`, `paired-edit-summary.json`: raw timing series.
- `measured/profiles/{edit-control,edit-cache}/run.wcprof`, `profile-summary.json`: phase evidence.
- `measured/correctness/*/stderr.txt`: sentinel failures and six-test restoration proofs.
- `measured/restoration.json`: original and copy integrity checks.
