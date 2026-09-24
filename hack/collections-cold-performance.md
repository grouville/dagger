# Collections discovery: reducing first-use work

Measured September 24, 2026, after the [normal-mode warm comparison](collections-normal-mode-performance.md).
The current priority is cold startup while preserving warm and edit behavior.
The 500 ms warm target remains unmet.

## Change: use the shipped TypeScript SDK bindings

The engine bundles the TypeScript runtime module's generated Go files, but its
legacy `runtime/dagger.json` asks the Go SDK to regenerate them on first use.
`codegen.automaticGitignore = false` does not disable runtime code generation
on this branch: the **configuration format** selects that behavior.

Migrating that internal module to `dagger-module.toml` selects the existing
committed-files path. The runtime source, generated bindings, module name and
engine API version remain the same. This removes one `codegen generate-module`
execution; the Go build still runs. There is no new cache, global registry,
expiry policy, or cached list of discovery answers. The packaged source and
ordinary Dagger graph continue to determine invalidation.

This change belongs in the engine's SDK payload. Replacing only the engine
executable in an old image will not apply it; rebuild the engine image.

## Cold measurements

Command: `dagger check -l --all`, including process exit. App `14d684f`, remote
Go collections `1784ff3`, full configuration including the backend base and
Playwright service. Both sides include the same experimental Dang syntax cache
and TypeScript bundle split from the previous report. Neither the persistent
metadata experiment nor the direct Node loader experiment is included.

Each sample starts with a ready engine and a **new, empty `/var/lib/dagger`
volume**. Docker's image, host page cache, DNS and upstream registry caches
are not cleared. These are first-use Dagger measurements, not machine boot
or engine-image-download measurements. Runs are serial, without `--extra-debug`,
with `wcprof` enabled from the first command and no profiler warmup.

| Order | Original SDK manifest | Committed-bindings manifest |
| --- | ---: | ---: |
| Control, candidate | 72.444 s | 41.211 s |
| Candidate, control; new volumes | 42.084 s | 38.793 s |

All four commands succeed and return the same complete 14-row output. The
second pair is a 3.291 s / 7.8% reduction. **Do not claim the first pair's
31.233 s difference as the effect of this patch.** The original first sample
also spent much longer importing SDK and Node images. A fresh Dagger volume
does not remove those sources of variability.

The profiler confirms the eliminated work: `codegen generate-module` runs once
in each control (18.78 s and 16.82 s), and zero times in the candidates. That
duration overlaps other work. The compiler also does more work concurrently
in the candidate, so removing a 17 s phase does not imply a 17 s wall-time win.
The first control's wcprof simulation has 26% drift; its predicted savings are
not used as measurements. All four profiles have no dropped or open events.

Kyle's 29.88 s cold remains a result from his machine and cache procedure.
These measurements do not reproduce his installed engine artifact or establish
the same absolute latency on his machine. No Cloud comparison has been run here.

## Warm behavior

Five serial alternating measurements after warmup give **3.087 s before and
3.124 s after**. This series does not demonstrate a warm improvement. All
listing output is byte-identical. The change targets first-use preparation;
the existing warm optimizations remain relevant independently.

## Validation and further work

The focused TypeScript integration run passes signatures/default arguments,
generated entrypoints importing user classes, telemetry imports and execution
error propagation. It exercises actual code generation and module calls,
beyond merely checking listing exit status.

Eight additional frontend calls pass using both the original and split SDK
bundles: original behavior, edited function body, deliberate runtime error,
and restoration. The expected file contents and error marker are checked,
not only the exit code.

The edit sequence also passes: comment-only change, renamed test, added test,
added module and restoration. Expected keys are asserted independently of
the control, and both full outputs are compared. Samples are retained,
including the candidate's 4.613 s rename outlier; they do not establish an
edit-latency improvement from this manifest migration.

An isolated compiler experiment added `-gcflags=./...=-dwarf=false` to the
already stripped Go runtime build. It completed the cold listing correctly in
40.386 s, with 36.08 s aggregate compiler time versus 35.79 s in the previous
manifest-only candidate. This does not demonstrate an improvement. The flag
is **not adopted**; its patch and profile are retained as a negative result.

## Prototype: package the SDK executable

The next experiment builds the fixed TypeScript SDK's Go program before
starting the engine. The static Linux amd64 executable is about 17 MiB and
is added to the existing SDK OCI payload. The loader constructs an ordinary
scratch container with that file and passes it as an explicit runtime input.
The runtime's content/recipe identity participates in module identity; no
engine-local handle is used as a portable cache key. Module dependency edges
retain the runtime through normal DagQL ownership and persistence.

The app's Go modules still compile normally. This is not a prebuilt
application or a stored listing. It moves the SDK's own build into engine
distribution; it does not make the build free.

| Sequential fresh-volume run | Seconds | Go build processes |
| --- | ---: | ---: |
| Prebuilt SDK | 40.538 | 2 |
| Source-built SDK, committed-bindings manifest | 53.299 | 3 |
| Prebuilt SDK repeated after control | 52.009 | 2 |
| Prebuilt SDK with finer import profiling; separate diagnostic run | 26.580 | 2 |

All four outputs match the 14-row reference. Compiler work drops from
38.98 s aggregate in the control to 17.60 s and 24.30 s in the candidates,
but this is overlapping work, not wall-time saved. SDK imports, Git fetches
and Node image materialization vary substantially too. **These samples do
not justify a stable end-to-end speedup percentage.** The second candidate
spends 28.65 s aggregate in builtin SDK imports and 18.95 s in Node image
materialization. These phases overlap and must not be added together.

Five warm runs give 3.050 s versus 3.001 s median: no substantial additional
warm improvement is established. The focused TypeScript integration cases
and eight original/edit/error/restore frontend calls also pass for this
prototype. Its twelve edit-sequence cases pass as well, including independent
checks for renamed/added tests, an added module and restoration. After stopping
and restarting the candidate engine on the same cache volume, the complete
listing and actual frontend build still return the expected results. This is
a focused persistence check, not a substitute for the full persistence suite.
The draft engine-builder integration compiles. The measured
binary was built locally with Go 1.26.6; a full release image build and other
architectures have not been validated.

The [experimental patch](collections-qa-performance-data/cold-priority/prebuilt/prebuilt-runtime.patch)
includes the loader, runtime handoff, cache identity and engine-builder
changes. It is **not enabled by a normal build of this branch**. To explore
it in a disposable checkout, apply that patch and rebuild the engine image
with `./hack/build`. The prior Dang/TypeScript bundle experiments are separate;
applying this patch alone does not reproduce their warm timings.

Before upstreaming, review the internal runtime override API, test payload
fallback and architecture selection, enforce generated-binding freshness,
and run the full affected SDK/persistence suites. Keep the SDK source and
binary in the same versioned build. A changed source/API/compiler/platform
must produce a different runtime artifact.

The separate diagnostic run adds three wcprof boundaries to the engine and
completes in 26.580 s. It is not paired with a new control, so it is neither
a stable cold expectation nor evidence that profiling made the command faster.
Its import timings distinguish the next target:

| Packaged SDK | Copy compressed content | Read metadata | Import root filesystem |
| --- | ---: | ---: | ---: |
| Go | 0.640 s | 0.0004 s | 4.512 s |
| TypeScript with prebuilt runtime | 0.563 s | 0.0009 s | 0.894 s |

The Go SDK filesystem import dominates its materialization in this run.
Reading the image metadata is negligible. These SDKs are already shipped
inside the engine image: these values are not a network download from
`registry.dagger.io`. Node's separate image materialization takes 3.16 s in
the same trace. All six added events complete successfully, with no dropped
events. The focused builtin-container metadata, failure and ownership tests
pass with the instrumentation.

The separate persistent-registration prototype removes both TypeScript
registration processes at warm cache, but its five-run median only changes
3.141 s to 2.866 s. It is not enabled by this change: runtime identity,
non-container fallback, persisted ownership and cross-workspace behavior need
further validation. Avoid trading those guarantees for an attractive timing.

Raw timing records, output, profiler summaries, scripts and validation summaries
are in [the evidence directory](collections-qa-performance-data/cold-priority/).
The initial prebuilt attempt returned a partial listing with exit zero due to
an incorrectly typed prototype argument; it is excluded. The benchmark runner
now supports `--expect-stdout` to reject that case directly.
