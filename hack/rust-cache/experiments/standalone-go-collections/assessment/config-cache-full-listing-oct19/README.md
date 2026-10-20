# Configuration cache choice: full-repository screening

The LRU is restored in draft [#14741](https://github.com/dagger/dagger/pull/14741). It keeps configuration parsing independent of engine/session context and bounds retention explicitly. Existing component measurements favor its lookup and miss costs. **An end-to-end advantage over the DagQL cache has not been established.**

The source and tests are byte-for-byte identical to the previously tested LRU commit `f2a21f27edf64b2d9a00e06e61ddb29e3a500292`. The restored commit changes its explanation, includes DCO and is recorded in `config-lru-restored-publication.json`. The previous DagQL description is retained in `14741-before-lru-review.json`.

## Current-main full-repository attempts

Each runs `dagger check --module go --check test --list --all` on the root Go module of the real Dagger repository, with the unchanged Go module `334136faaa1cd36ac26dfdc648eda907ce99c063`. The source inventory is revision `c5456d9cbf47e432b89aba43e35211425e8e1f03`; its test setting selects the root module, not nested modules. Every attempt edits an ordinary source file and adds a uniquely named test. Expected inventory is 4,483 rows. The source and test files are restored afterward.

| Engine | Outcome at 180 seconds | Rows |
| --- | --- | ---: |
| Main, no parse cache | Timed out; interrupted | 0 |
| Main plus LRU | Timed out; interrupted | 0 |
| Main plus DagQL cache | Timed out; interrupted | 0 |

**These are failed screening attempts, not successful timing samples.** There is one attempt per engine, with different retained cache histories. Their partial CPU/allocation counters cannot establish total-work savings or regressions. They do not validate a completed output, successful cleanup or a before/after speedup. No median or percentage gain is claimed from them.

Engines share base `ce6dc9f9403b52067f5831149eab4871f857185d`, image and GOMAXPROCS=8. The CLI and engine versions match at v1.0.0-beta.20. Main and DagQL binaries are those already verified in the sibling `config-dagql-integration-oct19` archive; the LRU binary is built from the previously verified commit. Build commands, hashes, engine identities, scripts, raw output and individual results are retained here.

Commands are sequential and start fresh CLI processes. Telemetry is enabled through the existing local collector; profiling is off. There are no forced garbage collections, cache-policy overrides or engine restarts. Existing engines and volumes are preserved. The screening scripts do not define these as cold starts or fully warmed whole-repository runs.

## What the earlier evidence does establish

The [earlier controlled development-engine experiment](../../../../NATIVE_CONFIG_DECLARATION_REUSE.md#earlier-full-command-investigation) changed only configuration decoding while holding the other optimizations constant. The complete 4,398-row listing improved **45.51 → 40.65 s**, with correct ordered output and successful cleanup in all four pairs. This is a real LRU-versus-no-cache result for that warm optimized engine. It is neither a new current-main result nor an LRU-versus-DagQL comparison.

The [current-main LRU component checks](../config-declarations-oct19/) reduce repeated lookups from **324.928 → 3.989 µs**, with a **4.7%** miss penalty. The full workspace race suite passes on main and that exact source/test tree. The [cache-choice component experiment](../config-cache-choice-oct19/) compares the two backing caches directly; it cannot substitute for a full-command result. The [DagQL implementation checks](../config-dagql-integration-oct19/) validate its real cache use and release but find no gain in the separate 16-package complete-command cohort.

The PR remains draft. Its description now puts the measured full-command result and its limits ahead of component benchmarks.
