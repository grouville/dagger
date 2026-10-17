# Pass registered built-in receivers directly

Complete edited Go test listing improves **46.84 → 45.71 seconds median**, faster in all four matched pairs. Cumulative engine allocation falls **36.81 → 34.82 GB** and engine CPU **240.65 → 229.25 CPU-seconds**. All commands return the correct ordered rows and exit successfully, including cleanup. Listing remains far too slow.

The patch belongs in Dang, the interpreter Dagger embeds to run modules. Registered built-in methods already accept their receiver as a value. Binding one currently creates a temporary type, nine type maps, an object and its scope, then immediately reads the receiver back out. The initialization comparison counts **1,474,958 bound built-in calls** in each arm of one listing.

A private callable passes that value directly to the registered implementation. Existing callable metadata, argument defaults and block handling remain in use. Hand-written `BuiltinFunction` callbacks retain the original fresh concrete `*Object` scope; their public callback field is not bypassed. Five primitive-method selection paths accept the new callable. The production patch introduces no cache, lock, cache-key change or telemetry suppression.

Registered methods now use a private concrete callable type. The interfaces used by the engine are covered here; an upstream port must also review embedders that inspect the old exported wrappers directly.

Four sequential component pairs evaluate parsed, type-checked expressions, validate their results and alternate original/candidate order:

| Expression | Before → after | Bytes/call | Allocations/call |
| --- | ---: | ---: | ---: |
| String prefix test | 2.30 → 1.14 µs | 2,081 → 880 | 26 → 12 |
| Three-element map with a block | 11.28 → 9.04 µs | 10,502 → 9,301 | 130 → 116 |

Every pair improves in both cases. A separate controlled-binary comparison retains exactly the original allocation counts with the candidate disabled. Its short string timings vary substantially, so it does not establish zero diagnostic overhead. Both full-command arms share that binary and registration setup; only the receiver-call path differs. Counters are disabled during measured pairs.

The complete command is `dagger check --module go --check test --list --all` on retained `dagger/dagger` source revision `ff0b029a4d270a651b9a8c7286babc79089066e4`, with module revision `7568cd0e5309a716fc94f310a488978fd97ce0c3`. Each invocation starts a fresh CLI and changes a used Go source comment. The engine and compiler caches are warm. Normal telemetry and GC stay enabled; CPU, lock and wcprof recording stay off. The previously measured sparse disk-usage sampling change is enabled in both arms.

| Pair | Temporary scope | Direct receiver |
| --- | ---: | ---: |
| 1, candidate first | 46.60 s | 45.89 s |
| 2, control first | 47.08 s | 41.39 s |
| 3, candidate first | 46.46 s | 45.52 s |
| 4, control first | 55.20 s | 47.79 s |

All eight measured commands return identical 4,398 rows. The excluded initialization pair adds a real test, returns 4,399 rows in both arms and takes 47.15 → 42.40 s. Removing that test restores the expected listing. Every attempt is retained. The median paired saving is 3.31 s, while the difference between column medians is 1.13 s; these are different statistics. The fourth pair has about 7% host I/O pressure in both arms. Its slower control remains included. These results must not be added to savings from another cohort.

The interpreter package and Dagger's v2 Dang SDK package pass race checks with both controlled modes. The pure candidate also passes the interpreter race suite. Two compatibility guards cover receiver binding, defaults, explicit arguments, context blocks, argument-map isolation and fresh custom callback scopes; they pass on the original implementation too. A subsequent metadata guard catches changed JSON error wording in the prototype. The final patch restores the original wording and checks callable names, types, parameter names and auto-call behavior. This wording-only correction follows timing; the measured sources are retained separately. An initial fixture compile error is retained alongside its correction.

The engine restarts gracefully on its existing volume, with no cache reset. All six native Rust histories reuse every compiler action before and on their first call after restart: 130/130, 1,026/1,026 and 6/6 on each side. The same checks pass after the full Go comparison and host-file tracing. Direct receivers and sparse usage sampling are now enabled on the owned engine; profiling and call counters are off, with ordinary GC enabled and no active session.

The [evidence archive](experiments/dang-builtin-receivers/) retains the [final standalone patch](experiments/dang-builtin-receivers/evidence/testdata/final-candidate.patch), exact candidate sources, inherited source references, controls, commands, every attempt, output and binary identities. The patch targets the exact library sources used here; it has not been rebased onto current upstream Dang. No new PR is open. The [configuration lookup investigation](NATIVE_CONFIG_LOOKUP_COSTS.md) identifies the next repeated engine operation without claiming a speedup for it.
