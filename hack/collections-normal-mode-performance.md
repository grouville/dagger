# Collections discovery: shared branch and normal-engine baseline

Measured September 24, 2026. With Kyle's current remote Go module and normal
engine flags, `dagger check -l --all` takes **6.435 s → 4.852 s median** with
the committed engine/CLI changes, a **24.6% reduction**. Adding the experimental
Dang syntax cache and TypeScript bundle changes gives **3.053 s**, a **52.6%
reduction** versus the original. These include CLI exit and telemetry shutdown.
The 500 ms goal remains unmet.

The [shared branch and build instructions](collections-performance-start.md)
explain what is enabled by a normal build. The roughly three-second result
requires experimental patches; those are preserved for review, not enabled in
the engine's normal source build.

## Kyle's changes are already public

The public refs were checked again before this audit:

| Repository | Collections head | Included in this comparison |
| --- | --- | --- |
| `dagger/dagger`, PR #14221 | `175dca038268639231c21323cd7aaa1d746617dd` | Original engine and CLI |
| `kpenfound/greetings-api` | `14d684fccf75a137de96f3f0c7eb8c6dafef2d3e` | Full app configuration |
| `dagger/go` | `1784ff37eb3dd1aacab7aaff91b1d86e311cc8de` | Unchanged in every variant |

Kyle's Go commit, "dont use go-include unless we have to", already removes the
helper build from listing. No newer commits appeared on those refs. Our older
scanner optimization and newer Go existence-check optimization are both
excluded from this comparison.

## Method and provenance

The original engine/CLI are built from the PR source. The committed variant
uses engine/CLI source `6e6bdfb16a`; subsequent branch commits are reports and
benchmark tooling. The experimental variant adds the previously isolated
syntax-cache engine and splits four dynamic imports from the generated
TypeScript SDK bundle into a small helper file.

All variants retain the remote `github.com/dagger/go@collections` declaration,
resolved to `1784ff3` in the recorded lock file. No local module substitution,
configuration trimming, removed service/base settings, or `--generated=false`
is used. The baseline and committed app are pristine; the experimental app
changes only the two SDK bundle files. The same ordinary Node runtime is used.

Earlier lab engines used `--extra-debug`, as the repository's development
launcher does. This audit restarts each variant without that flag. Each engine
reuses only its own benchmark-owned state volume after the former engine is
stopped; volumes are never shared between running engines. There are two
warmup rounds, followed by five serial measured rounds alternating order.
Profiles and correctness runs are separate. This is a warm-cache comparison,
not a cold startup measurement.

The host reports Intel Core i5-9300H, eight logical CPUs, Linux amd64. Engine
containers have no configured CPU or memory cap. Host load and exact binaries
are recorded with each run. Broken SSH-agent forwarding is omitted on all
sides; telemetry remains enabled.

The engine's exact published SHA image and the `collections` alias image were
not available during the check; the CLI checksum URL was also unavailable.
Therefore this is a **source-built baseline**, not proof of reproducing Kyle's
installed artifact. SDK/build source does not differ between the original and
committed source refs, and the measured engines share one SDK image.

## Warm results

| Round | Original collections | Committed engine/CLI | Experimental |
| --- | ---: | ---: | ---: |
| 1 | 6.342 s | 4.802 s | 2.884 s |
| 2 | 6.483 s | 4.852 s | 3.075 s |
| 3 | 6.435 s | 4.970 s | 3.053 s |
| 4 | 7.626 s | 4.852 s | 3.187 s |
| 5 | 6.322 s | 4.840 s | 2.972 s |
| **Median** | **6.435 s** | **4.852 s** | **3.053 s** |

The slower original sample is retained. Every full 14-row output is identical,
including order, flags, descriptions, and formatting. These results remain
close to the earlier development-engine measurements; removing extra-debug
and using the remote module did not eliminate the observed latency. Since
those two setup changes were made together, this is not an isolated estimate
of logging overhead.

An additional earlier pristine remote-module control on the extra-debug
engine gave 6.539 s warm median. Its first use of that project took 9.928 s on
an already-populated engine; that number is not a cold-start result.

## Edit and invalidation checks

One sequence writes fresh content and immediately runs the same command.
Expected keys are checked independently, and complete ordered outputs must
match across all three variants. These are individual samples, not medians.

| Edit | Original | Committed | Experimental |
| --- | ---: | ---: | ---: |
| Unchanged | 7.265 s | 5.744 s | 2.941 s |
| Comment only | 7.005 s | 5.149 s | 2.991 s |
| Rename a test | 7.121 s | 5.139 s | 2.972 s |
| Add a test | 7.163 s | 5.138 s | 2.993 s |
| Add a module | 7.965 s | 5.453 s | 3.118 s |
| Restore source | 6.412 s | 4.827 s | 3.014 s |

The unchanged committed sample includes first use of a separate identical
checkout created for the edit sequence; it is not another warmed median.
There are 14 rows normally, 15 after adding a test, and 16 after adding a
module. Sources are restored afterward. This validates discovery after edits;
it does not claim that every listed application check was executed.

## Profiling and remaining limits

Separate wcprof captures contain 28,139 / 21,196 / 21,462 operations for
original / committed / experimental, respectively. All have zero dropped
events and zero open operations. Engine trace spans are 5.76 / 4.43 / 2.51 s;
the corresponding whole commands take 6.234 / 4.881 / 3.043 s. Trace duration
is not a substitute for elapsed command time, and overlapping stage durations
must not be added.

Kyle's reported **29.88 s cold and 3–4 s warm** are observations on his own
environment. We do not have his build ID or cache-reset definition. These
measurements neither establish that our host is faster nor apply a warm
percentage to his cold time. Recent empty-engine-cache candidate attempts
failed on `cgr.dev` HTTP 500, so there is no new valid cold comparison.

Raw samples, source and binary identities, full configuration, the resolved
lock file, edit checks, scripts, and wcprof summaries are in
[normal-mode evidence](collections-qa-performance-data/normal-mode/).
The scripts preserve the actual local experiment paths and require prepared
engines; use the build guide for a new machine. No new production code was
changed for this audit; earlier focused unit, race, and integration validation
is linked from the previous reports.
