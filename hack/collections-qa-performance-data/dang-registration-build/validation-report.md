Focused current-dependency gates passed for the production registration snapshot. The six registration groups include a real DeclareDir import/self-type/@collection case; existing source-error rendering cases also passed. Normal package time was0.113s; race package time was1.961s. Nine runner steps completed: normal, race, one test-binary compile and six bounded micro invocations. No engine, Cloud or network workload ran.

| Public fixture | Two metadata parses | One owned metadata parse | Bytes/op before → after |
| --- | ---: | ---: | ---: |
| go.dang | 162.15 ms | 78.69 ms | 51,212,404 → 25,603,896 |
| gomod.dang | 133.43 ms | 65.61 ms | 42,403,448 → 21,201,694 |
| collection.dang | 3.75 ms | 1.88 ms | 1,254,650 → 627,740 |

These are medians of three alternating baseline/snapshot process pairs, with200ms requested per sub-benchmark. The larger source files complete only2–4 iterations per short run; all observations and iterations are retained in micro-summary.json. The baseline helpers are copied from the pinned current production source, changing only test symbol names. Both arms use ordinary Dang v2.1.4 ParseFile, the same public source bytes, fresh owned metadata per iteration and warmed source/page caches. This measures the two metadata consumers only: independent source declaration/inference, engine schema work and full CLI exit are excluded. Allocation bytes/counts are about50% lower; no peak-memory or whole-command reduction is claimed.

The first normal run stopped at a test-fixture panic: its lexical scope used NewObject(nil), while Dang Symbol.Eval expects a real type for import-conflict checks. The corrected test uses a real ObjectKind scope. Production source did not change; failed-v1 provenance and validation are retained. The final tested manifest is3cb4ec53886119511052e589f298134acbf71f5cc6643239dca96bfc9ba9c92f; patch4883894a15e4b30eddd690a96771fd50a2356790e9cb86af995be40515810f1e. Its source-only status records the pre-execution freeze; this report records the completed validation.

For production extraction, helpers.go, registration_metadata.go and registration_metadata_test.go form the functional patch and six focused witnesses. The baseline-copy and microbenchmark files are lab-only attribution fixtures; their hardcoded lab fixture path should not be copied into production tests. A maintained upstream benchmark would move those public source samples into suitable testdata and pin their provenance.

The historical38711 engine already omits object-directive retention and uses different Dang behavior. These results do not improve its already-measured1.1s timings. A valid next engine comparison uses current ordinary source/go.mod in both builds, adding only this snapshot to the candidate, with matching CLI/SDK/fixture pins. The prepared current-engine-plan.md specifies this comparison; no engines have been built or run.
