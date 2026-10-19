# Retain indexed owner facts in Go package collections

This module candidate improves complete test-edited listing **11.47 → 9.56 seconds median**, faster in all four balanced pairs. Ordinary-source listing improves **6.54 → 6.21 seconds**, also faster in all four pairs. The minimum paired test-edit saving is 1.33 seconds; median paired saving is 1.72 seconds. This is a useful candidate on the current experimental stack. Three seconds, current cold performance and a Rust latency gain remain unestablished.

| Complete-command measure | Full owner objects and scans | Indexed owner facts |
| --- | ---: | ---: |
| Test-file edit | 11.47 s | 9.56 s |
| Ordinary-source edit | 6.54 s | 6.21 s |
| Test-file edit, engine CPU | 60.71 CPU-s | 49.60 CPU-s |
| Test-file edit, allocated bytes | 13.68 GB | 11.08 GB |

The command remains `dagger check --module go --check test --list --all` on dagger/dagger `ff0b029a4d270a651b9a8c7286babc79089066e4`. Both arms use the same engine, CLI and common diagnostic settings, including prepared-schema reuse. Shared receiver decoding stays disabled. Every invocation starts a fresh CLI and makes a real source edit on the warm engine; test-edit commands also change a test-file comment. Both arms complete test addition and removal before four measured pairs per workload. All 24 timing commands return correct ordered names and identical full rows, and exit successfully. Telemetry, ordinary GC, final flushing and cleanup are included, with no concurrent profiler or heavy work during timing.

## Why this preserves the workflow

The baseline collection stores every full `GoModule` owner. Resolving one package reconstructs all 80 owners and their repeated settings, scans the module roots, then scans the owners. The earlier index-only screen improved the lookup but left this reconstruction intact and produced insufficient command-level gain.

The candidate retains the shared `Go` settings once in the collection and indexes each module's prefix and test-selection fact by path. The normal getter walks path ancestors, finds the deepest owner and constructs that one `GoModule` through the existing `goModuleAt` helper. That helper remains the single place that forwards version, base, flags, extra files, selection and mount settings. An explicit constructor builds the private map without exposing a map as a GraphQL argument. Balanced merges avoid repeatedly copying a growing immutable map.

All authored getters still execute. Per-key cache lookup, native source snapshots, test discovery, selection, expected failures, source overrides, ownership rebinding and actual test execution retain their existing paths. No engine code, library dependency, cache policy or lock changes are introduced.

## Evidence and checks

Lossless wcprof captures retain **804 evaluations, 1,494 SDK requests and 800 getter executions** in each arm. Test discovery executes once and hits 799 times. Getter receiver data falls **81.382 → 52.126 MB**, converted values **1.956 million → 931,200**, and converted lists **392,000 → 6,400**. Converted objects increase **64,800 → 65,600** because the small anonymous fact records still count as objects; this is not a claim that all receiver reconstruction has disappeared. The remaining 800 collection keys are still converted for each getter.

Nine focused checks pass: collection selection, source snapshots, discovery, module-layout rebinding, test collections, binaries, generation, ownership boundaries and owner settings. The settings check runs a selected test, executes a linked binary and checks generated content with a custom base, GOFLAGS, build flags, an extra input file and a custom mount path. An intentional negative control rebuilds the owner with default settings; the check fails because its required build tag is lost. The exact production source is then restored.

Only the development-check module gains that settings regression after timing and profiling. The measured main Go source is unchanged. The exact timed tree, final source, patches, successful checks and negative control are retained. Both profile streams have zero dropped or open operations. All diagnostic flags are restored, no client remains active, and all four retained engine binaries and cache volumes remain intact.

The comparison uses the retained engine after the earlier cancelled broad Rust fixture import; it does not reset that cache. Its results must not be added to earlier cohorts. This module change rests on the existing native-source and getter-identity development stack and has not been ported to upstream module main or measured on a released engine. The separate schema-reuse Go/Rust pipeline validation remains applicable to the unchanged engine; it is not counted as new Rust coverage here.

[Module implementation and regressions on the fork](https://github.com/grouville/go/commit/de633b12ed2aa02e42adb698a23fcecc13faf36d). [Every attempt, source tree, measurement and profile](experiments/go-indexed-owner-facts/). [Review description](PR_GO_INDEXED_OWNER_FACTS.md). No PR is opened.
