# Ownership reuse: controls and unresolved timing variation

The candidate is a direct change to Go main `334136faaa1cd36ac26dfdc648eda907ce99c063`. It retains module roots with the package collection and checks the current module-layout digest before using them. Existing behavior checks, including adding a nested module after retaining a package, pass. Earlier separate wcprof comparisons show the intended reduction from 64 module searches and 64 upward searches to one layout check. No new end-to-end speedup is verified by this study.

All cohorts use complete `dagger check --module … --check test --list --all` commands, fresh CLIs, source edits, normal telemetry, normal cache/GC policy, output validation and successful cleanup. The stock benchmark engine is source `80699ac67a1c72dc38d30c4186105cd9dd3afde6`, GOMAXPROCS=8; the module is current Go main, not the engine. Initialization runs are recorded separately. These are warm-engine experiments, not cold-engine results.

The first controller used two installed aliases. Its candidate comparison appeared to improve 31.53 → 26.33 seconds, but identical-code controls showed a comparable difference. Reject that as a speed claim. A fixed single-alias/source controller measured 21.67 → 26.53 seconds. Giving every invocation a unique test name still produced an inconsistent 21.72 → 18.85 seconds, faster in two of four pairs, while its same-code control was 14.52 → 26.25 seconds. All attempts remain recorded; none is a selected headline.

The final controller uses two engines with the same image, binary hash, flags and ordinary cache policy. Each sees a fixed module source/configuration, one alias and unique source/test edits on every command. Four alternating pairs for 64 packages across eight modules measure 21.40 → 20.17 seconds, faster in two pairs. The identical-code control is 21.65 → 28.67 seconds, also faster in two pairs. The differing cache work invalidates a dependable latency claim. Resource measurements suggest less work in the candidate, but that does not repair the timing control.

After timing, three consecutive diagnostic commands run the same unmodified main module on the same engine and fixture, each with a fresh source edit and test rename. All return 64 correct rows; wcprof records zero drops and no open operations. These profiled durations are not clean benchmark results:

| Diagnostic | Time | Engine CPU | Allocated | Package getters executed / cache hits |
| --- | ---: | ---: | ---: | ---: |
| First | 41.19 s | 125.18 CPU-s | 17.43 GB | 64 / 0 |
| Second | 14.55 s | 74.27 CPU-s | 10.21 GB | 0 / 64 |
| Third | 29.68 s | 119.97 CPU-s | 17.36 GB | 64 / 0 |

The slow runs also execute the 64 path helpers and rebuild function/source-map definitions that the middle run reuses. Top-level package discovery itself executes in all three runs. This identifies different work rather than host scheduling noise alone. It does not establish a cache bug: workspace inputs change on every invocation, and the cause of the different reuse has not been diagnosed. Idle lifecycle snapshots show no retained clients or active requests on either controlled engine.

The compressed raw traces, work counts, class reports, critical paths, exact controller and engine identities accompany this report. Prior full stdout/stderr logs and earlier diagnostic traces remain in the shared local experiment directory. No PR is opened for ownership reuse. Next verification must explain or control this difference in work, rather than select the fastest runs or add another controller without a causal explanation.
