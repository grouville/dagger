# Split PID1 startup: local runtime comparison

The prototype improved this warm check-listing series, but it did not establish a general improvement across navigation and edits. Keep it experimental: `list -a` was mixed and its two-sample median increased. All 36 measurement calls and the preceding 10 SDK/execution smoke calls were correct, with full fixture and engine restoration. No Cloud requests were made.

The change splits the container PID1 launcher from the heavy Dagger session helper. Both arms install the exact same heavy and light binaries. The control mounts the heavy binary at `/.init`; the candidate mounts the light binary there and the heavy session helper at `/.dagger-session`. The original CLI, Docker container connector, engine volume, SDK blobs, workspace configuration and default progress mode are identical. No result cache or module configuration was changed for timing.

| Ordinary flow | Samples per arm | Baseline median | Candidate median | Difference |
| --- | ---: | ---: | ---: | ---: |
| `dagger check -l --all`, warm | 6 | 1,423.13 ms | 1,346.10 ms | −77.03 ms / −5.41% |
| `dagger list -a`, warm | 2 | 1,404.97 ms | 1,479.04 ms | +74.07 ms / +5.27% |
| New app comment → `check -l --all` | 2 | 1,464.23 ms | 1,452.57 ms | −11.67 ms / −0.80% |
| New native input → `generate render`, full exit | 2 | 397.07 ms | 357.60 ms | −39.47 ms / −9.94% |
| Same native generation, file visible | 2 | 374.07 ms | 337.27 ms | −36.80 ms |

These are four ABBA engine blocks, each explicitly primed for both listings. The warm-check comparison is consistent within this trial: all six ordinal comparisons between adjacent baseline/candidate blocks are lower, with a median difference of −61.39 ms. These six observations are clustered in two blocks per arm, not six independent engine replications. The two artifact-list differences are +179.39 and −31.25 ms; the two comment-edit differences are −27.87 and +4.54 ms. The two native generation differences are −31.91 and −47.03 ms. More repetitions would be needed before claiming stable distributions or attributing the artifact outcome to the implementation.

All ordinary wall samples, in milliseconds and acquisition order within each arm:

| Flow | Baseline | Candidate |
| --- | --- | --- |
| Warm check listing | 1405.94, 1434.02, 1370.83, 1425.95, 1427.48, 1420.32 | 1344.82, 1338.37, 1319.12, 1364.28, 1347.37, 1361.40 |
| Warm artifact listing | 1362.94, 1447.00 | 1542.33, 1415.75 |
| Fresh comment listing | 1463.17, 1465.30 | 1435.30, 1469.84 |
| Fresh native generation | 396.95, 397.19 | 365.05, 350.15 |
| Native generated file visible | 371.24, 376.91 | 345.25, 329.29 |

Each edit used distinct never-evaluated bytes; their hashes are retained in `samples.json`. A unique source comment does not imply every lower cached result is new: unchanged discovery outputs can correctly reuse content-addressed work. File visibility uses 5 ms polling; full process exit uses a blocking wait thread. Native generation here writes a small file through a Dang generator. It is not Go/TypeScript/Python SDK code generation. The selected actual Go test and authored Go/TypeScript/Python execution paths were validated in the separately accounted smoke stage, not benchmarked as matched warm execution flows here.

The 36-call total includes eight block primers, 24 ordinary observations and two separate full-primer/profile pairs. Two fully primed diagnostic check listings produced the following evidence; their wall times are excluded from all medians above:

| Profile boundary | Baseline | Candidate |
| --- | ---: | ---: |
| `exec.processRun` count | 6 | 6 |
| Runtime-process interval union | 617.87 ms | 651.28 ms |
| `Workspace.artifacts` execution | 705.80 ms | 664.99 ms |
| `Artifacts.__itemsJSON` execution | 786.44 ms | 826.45 ms |
| Engine query interval union | 1,520.03 ms | 1,514.86 ms |

Both profiles have zero open operations and zero dropped events. These nested spans overlap and cannot be added as independent savings. `exec.processRun` includes the command itself, not just PID1 startup. The profiles preserve the number of runtime invocations but do not explain the ordinary warm-check gain causally. The separate 30-process startup microbenchmark established lower launcher startup cost; it is not a prediction of whole-command latency.

The earlier smoke exercised actual Go and TypeScript methods with ordinary function caching disabled in the existing modules, a Python default-factory module configured to force runtime dispatch, a newly changed selected Go test, and an ordinary uncached container command. The latter checked the actual `/.init` binary hash and candidate helper presence/hash from inside the execution container. All ten calls dispatched processes and returned the expected bytes or passed check. Initial TypeScript/Python preparation is visible in that smoke; its unequal setup times are not A/B speedups.

This is a retained-volume local comparison, not a fresh-volume cold or service-up test. The wide `/tmp` fixture ancestry is the same in both arms and already uses the explicit parent-metadata optimization. No automatic socket optimization, shared HTTP transport, parallel log export or module-load pipeline is part of this comparison. The smoke and measurement stages both removed only their newly owned containers, preserved the retained volume and left the original engine stopped with unchanged engine/helper binaries. Measurement command intervals recorded 3,588,096 bytes of engine writes; that counter excludes engine startup and gaps.

The result warrants further investigation, not immediate upstream adoption. The additional reserved helper mount, platform support, service/TTY behavior and compatibility need review beyond the passing PID1/orphan, unit/race and three-SDK gates. The 500 ms target remains unmet for full greetings artifact/check discovery in this stack.

`samples.json`, `summary.json` and `profile-phases.json` retain the complete numeric evidence. The explicit archive allowlist excludes raw profiles, stdout/stderr, container/session identifiers, original binary backups, tokens and generated fixture contents.
