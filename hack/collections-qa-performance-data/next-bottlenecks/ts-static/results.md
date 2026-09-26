# Static TypeScript metadata: measured prototype

The warm listing improves from **2.643 s to 2.132 s median (19.3%)**, using eight alternating pairs of the real `dagger check -l --all` on the copied Kyle greetings workspace. All 14 rows match byte for byte. This is a new isolated prototype on top of the previously optimized stack, not a released SDK change and not the original branch's baseline.

Both variants use the combined Dang candidate and existing prebuilt TS SDK/direct Node/split-import/compile-cache stack. `core/artifact_batch.go` is frozen to `c12a34663b` for parity; the new batch optimization is excluded. Two task-owned engines and their existing volumes are preserved. Binary hashes and configuration are in `engine-manifest.json`; full rows, timings and profiles are under `measurements/`.

| Real action | Control median | Static TS median | Repetitions |
| --- | ---: | ---: | ---: |
| Warm listing | 2.643 s | 2.132 s | 8 pairs |
| Comment edit | 3.047 s | 2.558 s | 3 pairs |
| Rename test | 2.748 s | 2.429 s | 3 pairs |
| Add test | 2.832 s | 2.582 s | 3 pairs |
| Restore source | 2.823 s | 3.259 s | 3 pairs |

The edit medians are noisy and restoration regresses in all three pairs (+199/+189/+436 ms). These results do **not** establish a universal dev-loop win. Every edit was an actual write to `main_test.go` followed by the ordinary command; rename/add assertions check the new name/row immediately, and source is restored at the end. The static metadata fixture is unchanged during these application edits. Host IO full-stall time is only 1–13 ms in these measured runs, so the restoration regression cannot be attributed to hundreds of milliseconds of full-machine IO stalls on this evidence. Cold startup has not been measured for this candidate.

## Where the measured warm gain comes from

The control wcprof records two actual Node process intervals, 732.8/734.0 ms, overlapping. The candidate has **zero** frontend Node registration processes. This is the executor's started-process → exit interval, not a `withExec` resolver including prerequisites.

The first discovery query shrinks from 1,070 to 630 ms. Each new static metadata path takes 127/131 ms, overlapping: approximately 78–79 ms in conservative input validation/scope setup and 48/53 ms evaluating the generated Dang TypeDefs. Six existing Go processes remain. Profile wall span falls from 1.831 to 1.418 s, with zero dropped events and zero open operations in both captures. Profile times are not unprofiled command medians.

The first query's remaining graph also contains repeated `git.publicAdvertisement` calls around 94–214 ms. The second listing query remains 745 ms: configured backend constructor plus `goTestBase` takes 266 ms, `Go.modules` 290 ms, then overlapping `GoModule.tests` calls up to 120 ms. These are dependencies on the critical path, not additive global CPU sums.

## Correctness and scope

- Exact unchanged listing parity: passed.
- Original TS `source entries` and `build entries`: match control. This exercises constructor defaultPath, state rebuild, method invocation and return-ID serialization using the **original TypeScript runtime**.
- Edited TS API, compiler config, generated binding or an added source file: explicit stale-metadata rejection, not old schema reuse.
- Restored inputs: listing recovers.

This initial fixture intentionally fails closed on TypeScript metadata-input edits. Automatic authoritative regeneration is not implemented, so it is not the final edit UX and should not be merged as a permanent fixture hook. `design.md` describes the existing generator integration and common ModuleEntrypoint direction. The missing automatic path must be supplied before presenting this as a general SDK optimization.
