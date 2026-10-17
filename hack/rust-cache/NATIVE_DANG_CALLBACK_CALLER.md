# Reduce allocations in Dang collection callbacks

Two alternating before/after orders of the full Go listing measure a median **83.77 → 82.22 seconds**. All commands succeed and return the same 4,398 rows. The change removes about 1.25 GB of cumulative allocation per command, but does not resolve the listing bottleneck. It remains an opt-in experiment, disabled after measurement; no PR is opened.

`callFunc` creates a dummy object and type for every callback, including nine empty maps. Concrete Dang `FunctionValue.Call` only reads that caller's `self`; locals and arguments are allocated separately from the function's closure. The prototype shares the empty caller only for that concrete implementation. Other `Callable` implementations keep fresh callers because they can mutate them. There is no new production lock or cache of user values.

The focused race checks cover concurrent arguments, captured self, mutable custom callables, and the existing block/return/continue/self/closure cases. Real Go module ownership and test-collection checks pass with fresh inputs. A graceful engine replacement preserves all six recorded native Rust action histories. The initial captured-self test fails identically on the control; its corrected explicit-self fixture passes. Both observations are retained.

| Order | Original caller | Reused caller |
| --- | ---: | ---: |
| Before, after | 83.25 s | 82.23 s |
| After, before | 84.29 s | 82.20 s |
| Median allocated bytes | 43.38 GB | 42.14 GB |
| Median engine CPU | 263.40 s | 258.43 s |

These are warm-engine commands with a new CLI and a fresh Go source comment every time, against dagger/dagger `ff0b029a` and the same Go module `b5dd9434`. Telemetry and normal GC remain enabled. Both arms use declaration reuse, telemetry metadata batching, the selected attribute decoder and snapshot seeds. Flush coalescing and metadata read-ahead remain off. No compiler/test workloads run during listing. This is a comparison on the existing experimental engine, not stock upstream Dagger.

The callback-only benchmark measures 2,230 → 1,391.5 ns, 2,648 → 1,464 bytes and 30 → 17 allocations. Its larger relative gain is not the complete-command gain. Two full-command pairs do not establish a stable percentage improvement.

The previous wcprof capture also identifies a serial package-discovery chain: `Go.packages` takes 42.51 seconds, including 80 `GomodGoMod.ownFiles` calls. The next isolated Go-module experiment evaluates independent per-module discovery through Dang's existing ordered parallel selection, then concatenates the results in source order. It retains the collection API and test granularity.

[Source, race logs, complete measurements, engine identity and native-cache retention evidence](experiments/dang-callback-caller/).
