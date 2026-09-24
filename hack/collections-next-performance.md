# Discovery performance: another second removed, 500 ms still ahead

The [normal-engine audit](collections-normal-mode-performance.md) is now the
reference for trying this branch: **6.435 s original → 4.852 s committed →
3.053 s experimental**, using Kyle's unchanged remote Go module. It removes
`--extra-debug` and checks the full output again. See the
[build/start instructions](collections-performance-start.md).

The earlier experiments below used `--extra-debug` on both engine variants.
They remain useful matched development-engine measurements, but should not be
silently compared with a user's installed engine.

Measured September 24, 2026, using Kyle's exact `dagger check -l --all` in
`kpenfound/greetings-api`. The final matched comparison is **6.465 s → 3.016 s
median, 53.4% less elapsed time**, including CLI exit. All 14 normal listing
rows remain identical. After real edits, the candidate takes **2.96–3.47 s**.

The candidate includes experimental Dang syntax caching and TypeScript SDK
packaging. **This is not the performance of the production commits alone, and
it does not meet 500 ms.** The last production-only comparison with Kyle's new
Go module was 6.731 → 4.997 s; see the
[previous report](collections-kyle-latest-performance.md).

## Final before/after comparison

Both sides use app `14d684fccf75a137de96f3f0c7eb8c6dafef2d3e`, the full original
SDK/lint/Playwright configuration, pinned dependencies, and local Go module
sources. The baseline uses collections PR #14221 at
`175dca038268639231c21323cd7aaa1d746617dd`, with Kyle's scanner-free Go module at
`1784ff37eb3dd1aacab7aaff91b1d86e311cc8de`.

The candidate combines the existing CLI/engine commits, the isolated Dang
syntax-cache engine, the Go existence-check commit described below, and the
Node SDK bundle experiment. It excludes the Node compile-cache and Bun
experiments. The original Go-helper scanner optimization is also excluded:
Kyle has already removed that helper from listing.

Five serial rounds alternate variant order, after warming each variant.
Profiling and correctness suites run separately. The broken SSH agent is
omitted on both sides; normal telemetry remains enabled.

| Warm round | Original collections | Full experimental candidate |
| --- | ---: | ---: |
| 1 | 6.302 s | 3.016 s |
| 2 | 6.468 s | 3.122 s |
| 3 | 6.465 s | 2.872 s |
| 4 | 6.502 s | 3.075 s |
| 5 | 6.400 s | 2.957 s |
| **Median** | **6.465 s** | **3.016 s** |

The edit sequence writes new source content and immediately runs the command,
without warming that edited input. Expected keys are checked independently;
the complete ordered outputs must also match between variants.

| Edit | Original collections | Full experimental candidate |
| --- | ---: | ---: |
| Unchanged | 6.513 s | 3.250 s |
| Comment only | 8.765 s | 2.997 s |
| Rename a test | 7.995 s | 3.356 s |
| Add a test | 7.356 s | 2.959 s |
| Add a module | 7.844 s | 3.474 s |
| Restore source | 6.542 s | 2.952 s |

These are one edit sequence, not edit medians. There are 14 normal rows, 15
after adding a test, and 16 after adding a module. Sources are restored.
Kyle's reported 29.88 s cold and 3–4 s warm remain observations from his own
environment, not the control measurements in this table.

## The new TypeScript finding

An instrumented import diagnostic attributed **1.16–1.20 s per process** to
loading the frontend's generated `sdk/core.js`. Loading the generated client
took about 80 ms; loading the application itself took about 4 ms. Two fresh
TypeScript registration processes run during this listing.

The SDK bundle is about 4.1 MB. Its only four dynamic imports load Node's
`http` and `https` builtins. The bundled `tsx` 4.15.6 loader rewrites dynamic
imports for interoperability and generates a source map for the containing
file. Thus four imports trigger source-map work across the large bundle, even
though that bundle is already JavaScript.

The successful experiment moves those imports into a tiny ESM helper, imported
statically by `core.js`. The helper functions still perform lazy `import()`;
HTTP loading is not made eager. The loader processes a small file when it
rewrites those imports. It still reads/parses the main bundle: this does not
make total SDK loading constant time.

An isolated five-round comparison, with the same engine, CLI and unmodified
Kyle Go module on both sides, measures **3.965 → 2.923 s median (26.3%)**.
The candidate range is 2.905–4.044 s; the slow sample is retained. Its separate
edit sequence takes 2.97–3.55 s versus 3.99–4.65 s. These are separate samples
from the final combined comparison above; percentages should not be added.

`wcprof` records **21,419 operations on each side, no dropped events and no
open operations**. The two TypeScript execs drop from approximately 1.94 s
each to 0.99 s each. They overlap, so their durations must not be summed into
an end-to-end saving. Trace duration drops from 3.40 s to 2.31 s in these
separate profiled runs.

This changes packaging, not Dagger result-cache policy. Edited source still
invalidates ordinary content-addressed inputs. Actual frontend calls also
passed: returning source files, executing a changed method body, propagating
a thrown error, and restoring the original behavior.
An additional control/candidate/control sequence gives the two workspaces
different website contents and verifies that `defaultPath` selects the correct
input each time in the same engine.

**Upstream status:** this is a reproducible generated-bundle prototype, not a
production SDK patch. Shipping requires implementing the packaging change in
the SDK builder or fixing the loader, validating generated clients and source
maps, and covering supported runtimes. Hand-editing a generated SDK alone is
not a complete fix: regeneration can replace it and staleness checks can flag
it. The patch and exact source hashes are preserved with the evidence.

## A committed algorithmic improvement in the Go module

Commit **`59d9ca5cff3dcacc2677cdd2e1db29c7a43074a4`** on
[`grouville/go:perf/discovery-existence`](https://github.com/grouville/go/tree/perf/discovery-existence) changes
`GoMod.isGoModule` to check the unsorted owned-file list. It previously called
`ownFiles`, whose insertion sort orders all files, merely to ask whether the
list is empty. Public `ownFiles` output remains sorted exactly as before.

This removes the O(F²) sorting term from existence checking. Ownership still
includes scanning and checking nested roots: the change does not claim O(1)
existence or eliminate all quadratic work elsewhere. In particular, public
file sorting and repeated file-to-test-match joins remain separate targets.

Three measured rounds per synthetic fixture, with identical listings:

| Go files in one module | Original | Avoid existence sort |
| --- | ---: | ---: |
| 64 | 1.144 s | 1.090 s |
| 256 | 1.271 s | 1.127 s |
| 512 | 1.647 s | 1.220 s |

That saves about 427 ms at 512 files. It is a scaling improvement, not a claim
that greetings-api saves 427 ms. A separate five-round Go-only greetings-api
comparison gives 4.038 → 4.214 s medians, with substantial variance, including
a 7.122 s candidate sample. It does **not demonstrate a gain on that small
application**. All samples are retained.

Eleven real module checks passed: five gomod checks and six GoDev checks,
including discovery, collections, test discovery, introspection and scanner
agreement. The new regression check covers ignored files, nested-module
ownership, file ordering, and adding/removing owned files. This commit is an
upstreamable candidate independent of the experimental engine and SDK caches;
a mail-format patch is included. It is separate from the Dagger engine branch.

## Experiments that did not provide the main gain

Each row has its own matched five-round control. Do not compare controls
across rows as if they were one simultaneous benchmark.

| Experiment | Control median | Candidate median | Interpretation |
| --- | ---: | ---: | --- |
| Node compile-cache volume | 3.926 s | 3.790 s | About 136 ms; does not remove the loader's source-map work |
| Convert SDK bundle to CommonJS | 3.937 s | 4.050 s | No gain; the CommonJS hook rewrites dynamic imports too |
| Use the supported Bun runtime | 4.017 s | 3.234 s | Variable, 2.830–4.374 s; an optional runtime change, excluded from the candidate |

The initial CommonJS conversion failed because `import.meta.url` was lost.
The measured comparison corrected that with the equivalent CJS file URL;
its output then matched. The failed setup was not counted as a latency sample.

## Cold starts and the next obstacles

With an already-ready engine and an empty engine-cache volume, the control
completed in **42.566 s**. The candidate failed twice, on separate empty
volumes, because **`cgr.dev` returned HTTP 500** for the pinned
`chainguard/wolfi-base` manifest. This is **not `registry.dagger.io`**, and the
errors do not establish rate limiting. Failed command durations were 103.199 s
and 41.378 s. They are failures, not cold-performance samples. There is no
valid new cold speedup comparison.

The error exposes an expensive dependency of discovery itself: resolving the
configured Go `base` invokes `dag://backend/go-test-base`, which resolves the
Wolfi image before checks execute. Removing the Go helper from listing did not
remove this eager preparation. A proper improvement must preserve the base
configuration for actual checks while avoiding its materialization when
listing does not need it. This matches the already-reported laziness problem
in [Dagger issue #14283](https://github.com/dagger/dagger/issues/14283); it is
not a new issue discovered by this investigation.

The final candidate's `wcprof` still shows two TypeScript processes, six other
runtime execs, repeated schema decoding and Git resolution. Its 2.37 s engine
trace accompanies a 2.87 s profiled whole command. Overlapping class totals
are not additive, and the analyzer's final-root what-if output is not a
reliable projection of whole-command latency here.

A separate CLI CPU/trace capture records 550 ms of CPU samples, including
about 180 ms in filesync directory walks. No CPU sample lands in the Git-label
loader in this small checkout; the earlier roughly 220 ms finding in the large
Dagger checkout should not be transferred here. The synchronization profile
records about **380 ms in telemetry shutdown**. This is observed waiting, not
a fixed sleep or proof that telemetry can simply be removed. Aggregate wait
totals span concurrent goroutines and exceed elapsed time.

For the **500 ms edit-loop target**, the next useful milestones are structural:

* Reuse unchanged registration/type metadata through Dagger's tracked inputs
  and retained recipe dependencies. Avoid starting Node merely to reconstruct
  unchanged metadata. The SDK `ModuleTypes` path is worth investigating;
  sharing mutable modules or schemas across caller/session scopes is not an
  acceptable shortcut.
* Defer container-valued check configuration until the operation needs it.
  Listing should not require the test image solely to compute a parent
  constructor's inputs.
* Reduce repeated Git resolution and filesync work while preserving credential
  scope, workspace lock refresh, and edit detection. A global URL cache or an
  mtime-only answer cache would change those semantics.
* Reduce telemetry completion latency while preserving final spans and logs.
  CLI exit remains part of the measurement.

These are remaining work, not measured fixes or a guaranteed 500 ms budget.
The validated current result is approximately three seconds on this workload.

## Evidence and reproduction

[Raw samples, scripts, profiles and patches](collections-qa-performance-data/next/)
include every measured warm sample, edit checks, cold failures, source pins,
CPU/synchronization summaries and wcprof analyses. Full binary profiles remain
under `/tmp/collections-perf/next-final` and `/tmp/collections-perf/ts-cache`.
The archived drivers use these explicit local paths and require the prepared
engines/workspaces; the generic runner is `hack/bench-artifact-discovery.py`.

The complete listing, not just exit status, is verified. An early packaging
failure demonstrated why: a listing can exit successfully while reporting a
skipped module. These tests are discovery and focused module/runtime QA; they
do not claim that every application check or every collections-spec case was
executed. Previously reported collection API parsing/description issues are
not fixed by this work.
