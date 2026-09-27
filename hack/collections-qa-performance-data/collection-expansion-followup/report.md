The next module change is now committed and pushed as [93d0f1b](https://github.com/grouville/go/commit/93d0f1b5288ccaa47aa4d5befd809a25f6ffb801), on `grouville/go:perf/discovery-path-normalization`. It changes only `gomod/main.dang`: a private pure helper replaces nested public module calls that only normalize path strings. The public method delegates to the same logic; workspace reads, file ownership, source invalidation and API signatures remain intact. The source is byte-identical to the previously validated candidate (SHA-256 `a709d13d64bab0dcd58e26e55338e235246d8f6721b08ef559f50dfc7680a184`).

The existing discovery and lookup checks passed for that exact candidate, including nested cwd, enclosing roots spelled `..`, and include/exclude filtering. Eight historical warm pairs measured 2.6304 → 2.5464 s. That is an older-stack measurement, not a current-stack prediction; it did not establish an edit or cold improvement. A new matched comparison must use local source refs on both sides. The active remote greetings pin remains 1784ff37 until explicitly changed. The separate pushed existence-sort optimization (`59d9ca5`) is not this patch.

In the latest saved Unix-connector diagnostic, `Artifacts.__itemsJSON` occupies 551.05 ms. It contains an initial configured-base resolution of 208.77 ms, a Go.modules invocation of 224.67 ms, then three repeated configured-base resolutions overlapping about 31 ms before parallel test discovery (maximum 76.85 ms). Cross-session operations temporally inside the module phase still contain three workspaceRootPath calls of 14.99, 31.74 and 17.08 ms. Source inspection ties those calls to the private-helper target. Nested inclusive durations overlap; they must not be added as independent savings. These are diagnostic calls outside the ordinary timing series.

A request-local cache of evaluated artifact prefixes is held. The current expansion DAG shares node/key enumeration, whereas evaluation re-enters ancestor DynamicInputs. Reusing the selected parent could suppress NEVER/PER_CALL constructor calls or live workspace observations between collection stages. Request-local scope alone does not prove equivalence. Its observed opportunity here is around 31 ms, not the entire expansion. The safe module-owned helper is the priority.

The two actual backend Go invocations expose a more general startup target:

| Recorded interval | Constructor | goTestBase |
| --- | ---: | ---: |
| Complete module call | 82.81 ms | 94.34 ms |
| runc-monitor interval labeled processRun | 71.54 ms | 82.23 ms |
| Monitor started → first nested serveQuery | 58.17 ms | 66.65 ms |
| First → final nested serveQuery | 8.62 ms | 10.96 ms |
| Nested serveQuery count | 8 | 10 |
| Nested schemaBuild sum | 0.515 ms | 0.524 ms |
| Last query → monitor exit | 4.75 ms | 4.63 ms |
| Monitor exit → module call completion | 7.84 ms | 8.75 ms |

The existing `exec.containerStart`/`exec.processRun` split does not mark entry into authored code. In pinned go-runc v1.1.0, `Run` sends `cmd.Process.Pid` immediately after launching the **runc monitor process**. Dagger's `procHandle.WaitForStart` invokes the profiling callback on receiving that PID. Namespace/container setup, shim and language initialization, and nested admission therefore remain inside the interval currently labeled user work. The generated Go dispatcher reads FunctionCall metadata before invoking the authored function; its first recorded query is that metadata access. The 58/67 ms prefix is consequently pre-dispatch work, but current records cannot divide it among runc, shim/Go startup and unprofiled nested-client admission.

The next generic diagnostic should distinguish actual shim/module entry and nested HTTP admission from the existing monitor-start marker. It should retain fixed phase names and numeric durations only, preserve full cleanup, and compare a trivial constructor with a normal method. No new instrumentation, runtime, or speedup claim is included in this audit. Source snapshots and profile hash are retained; raw wcprof payloads remain private.
