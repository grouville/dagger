# Sharing module-marker imports does not establish a listing gain

The independent confirmation gives **38.66 → 39.06 seconds** for the complete Go test listing on `dagger/dagger`, faster in four of eight pairs. Sharing the `go.mod` snapshot removes repeated filesystem calls but does not establish a command-time improvement. The candidate remains unselected; no new PR or upstream proposal is added.

The initial four pairs give **45.42 → 36.59 seconds**, faster in three pairs. Control timings vary substantially, so eight additional alternating pairs were fixed before running confirmation. Both cohorts remain in the record. The initial gain is not confirmed, and the cohorts are not presented as additive savings.

| Confirmation pair | Existing marker reads | Shared native snapshot |
| --- | ---: | ---: |
| 1, candidate first | 40.12 s | 39.79 s |
| 2, control first | 35.55 s | 35.26 s |
| 3, candidate first | 38.62 s | 39.00 s |
| 4, control first | 36.31 s | 40.02 s |
| 5, candidate first | 34.62 s | 39.80 s |
| 6, control first | 38.71 s | 39.11 s |
| 7, candidate first | 39.31 s | 35.25 s |
| 8, control first | 40.55 s | 35.15 s |

Each invocation starts a fresh CLI and edits a used source file on the same warm engine and retained volume. This measures an edited listing, not a cold engine. Telemetry and ordinary maintenance remain enabled; profiling is off during timing. Both arms include CLI exit, cleanup and an explicit final log flush. No admitted observation is discarded. Each cohort has one excluded initialization pair that adds a real test and lists 4,399 rows; removing it restores the expected ordered 4,398 rows. All twenty-eight commands, including initialization, succeed with correct output.

Confirmation median engine allocation changes **29.47 → 29.21 GB**, and CPU **195.60 → 187.58 CPU-seconds**. These are resource measurements, not elapsed-time savings. They do not justify the change as a listing performance improvement.

## The implementation and its limits

`Gomod.modules` currently reads each discovered marker through `Workspace.file`. The prototype obtains one sparse native `Directory` containing `**/go.mod`, synchronizes it once and reads markers from that immutable result. Enclosing modules above the workspace's current directory retain the original file path. Module validation keeps the same module-line expression, nested-module boundaries, ignored files, ordering and Go-file ownership checks. The existing public `isGoModule` method remains available. No engine API, extra cache or process is introduced.

The first prototype binds a lazy directory expression. Its diagnostic records 83 `Workspace.directory` calls because subsequent marker reads repeat the query prefix. The refinement uses the ordinary `Directory.sync` boundary. Both versions and their captures remain archived.

A lossless capture of the refined version records 1,079,601 events with zero dropped or open operations, and correctly links all 7,822 SDK requests to their backend operations. Against the earlier selected-module diagnostic:

| Recorded calls | Earlier selected module | Refined candidate |
| --- | ---: | ---: |
| `Host.directory` | 2,508 | 2,349 |
| `Workspace.file` | 2,258 | 2,098 |
| `Workspace.directory` | 2 | 4 |
| `gomod:Query.gomod` | 4,333 | 4,333 |
| SDK requests | 7,820 | 7,822 |

These are call counts from different engine binaries, not a matched latency comparison or counts of physical imports. Most work remains. The diagnostic takes 55.47 seconds with profiling; it is not a timing sample. The work-count analyzer initially attached the earlier lazy capture's result metadata while counting the correct refined capture. The archived correction reads both from the same capture and checks recorder identity. No benchmark observation is changed or rerun.

## Correctness and scope

All 36 library and Go development checks pass sequentially after refinement. A behavior check also passes against the original library: it covers directory-backed workspace edits, invalid markers, nested ignored-only modules, spaces and Unicode, and discovery from a subdirectory. Existing checks cover test collections, retained packages after module-layout edits, custom bases, generation, mounts and Go configuration. There are no timing assertions.

Source files, module configuration, diagnostic flags and profilers are restored after both cohorts. All six retained native Rust histories hit every action after the initial comparison and again after confirmation: 130/130, 1,026/1,026 and 6/6, twice each. No engine replacement or cache reset occurs during this experiment.

The code remains an isolated prototype. The next investigation should target repeated field preparation and module-client setup in the existing lossless profile, rather than infer a larger gain from fewer marker calls. The [archive](experiments/go-module-marker-snapshot/) retains exact sources, drivers, every observation, both captures, analysis corrections and retained-cache checks. The previous schema experiment has a separate [assessment](NATIVE_GO_OBJECT_SCHEMAS.md).
