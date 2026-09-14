# Collect parser choice statistics only when requested

2026-09-14. **Library revalidation of an earlier candidate, not a new discovery.**
No Dagger CLI measurement has been made for this particular implementation.
This branch contains an external-generator patch and measurements, not a Dagger
dependency bump or deployed engine change. The Rust goal remains unmet and the
[ordinary-flow scorecard](../bench-rust-toolchain-packaging/RELAY.md) is unchanged.

## Earlier experiment and disposition

The same opt-in choice-counting optimization was already published on
[`experiment/parser-choice-statistics`](https://github.com/grouville/dagger/blob/dba69fe62c23080ec606f434c80852421bea9447/hack/bench-parser-choice-statistics/README.md),
including a supported engine comparison and portable reproduction material.
That checkpoint was rediscovered after this branch's first commit. This branch
revalidates the mechanism on different Rust module fixtures; it must not be
counted as an additional optimization or added to the earlier results.

The earlier implementation uses a nil choice map to represent disabled
collection. This variant preserves the initial empty map and adds an explicit
enabled bit. Both restore collection state through undo/redo and retain
expression limits. There is no measured advantage of this variant over that
earlier implementation; the new library A/B compares with unmodified Pigeon,
not with the earlier candidate.

The earlier three engine pairs showed mixed CLI results: unchanged checks
saved a paired median 13.5ms, application edits regressed 4.0ms, workspace edits
saved 30.5ms, and external-library upgrades regressed 10.5ms. They establish
neither a general dev-loop win nor a causal cold-start win. Those are historical
measurements on upstream 7c35e627 with a different experimental stack, CLI and
module, not measurements of this branch based on c305ed37. Earlier cold wcprof
replay drift of -4.6% to -5.0% also fails our present absolute 2% replay gate;
do not use it for precise cold what-if estimates.

Keep both implementations as review evidence. Do not build another expensive
engine A/B solely to rediscover this mechanism: first establish why the variant
or current-main integration warrants it. The remaining cold image-delivery and
ordinary CLI costs are the next priority; no dependency adoption is implied.

## Context and change

Maintained wcprof on the latest ordinary Rust exact check attributes 40.4ms to
module construction self-time and 48.5ms to Rust.check self-time. These identify
an area to investigate, not a parser-only attribution. A subsequent parser-only
CPU profile on the actual 72-line check and 257-line generator modules identifies
choice-statistics collection as 20.60% of cumulative sampled CPU; allocation
sampling attributes 32.00% of objects cumulatively to it, including formatting.
Inclusive profile percentages overlap and are not wall-time savings predictions.

The Pigeon-generated parser counts/formats grammar-choice outcomes even when no
caller requests its Stats. The patch makes this internal diagnostic opt-in via
the existing Statistics option. Requested counters retain their exact values.
The returned undo option restores the Stats pointer, no-match label and enabled
bit, including undoing back to the default disabled state. ExprCnt, expression
limits, initial empty Stats map, Debug, Memoize and grammar remain intact.

This does **not** disable Dagger telemetry/wcprof, bypass the module runtime,
retain a hidden listener, change egraph/Cargo identities, omit work or drop output.
Same-package users inspecting private default parser counters observe an intended
behavior change; no such production Dang consumer was found. Compatibility
review is still needed and no upstream maintainer approval is claimed.

## Paired library results

Six alternating AB/BA pairs; same sources, Go 1.26.8, GOMAXPROCS=2, one heavy
process at a time, 500ms Go benchmark duration per input, file I/O outside timing.
Measured host: Linux/amd64, Intel Core i5-9300H.
All observations are retained in [samples.csv](samples.csv). Medians below are
per-parse, not per CLI invocation; do not multiply them by unverified call counts.

| Input | Control median | Candidate median | Median paired saving | Favorable pairs |
| --- | ---: | ---: | ---: | ---: |
| Rust check module | 10.464508 ms | 7.938447 ms | 2.546356 ms | 6/6 |
| Rust generator module | 46.953762 ms | 35.683097 ms | 11.508467 ms | 6/6 |

Check paired savings range 2.439863–2.593614ms, median 24.336337%.
Generator range 11.199526–16.718190ms, median 24.560923%.
First-pair allocation counts: check 71587 -> 47617 objects/op; generator
319965 -> 212353. No outliers discarded or historical gains added.

## Correctness executed

- 751 identical structural AST/location/comment/raw-error/recovered-error/
  formatted-output entries across the installed 480-file Dang corpus, two Rust
  modules and boundary/malformed-input cases. AST/error string bytes are encoded
  losslessly; function symbolic names are retained but are not semantic proof.
- 15 identical requested-statistics snapshots, including default/explicit
  expression limits, preseeded/reused Stats and memoization. Separate undo/redo
  assertions test the intentionally different default collection behavior.
- Both arms: focused format/highlight/option race tests, three repetitions;
  18 root passes each, no failures/skips (control 3.036s, candidate 2.530s).
- Both arms: existing TestDang/TestLanguage suite; 269 child cases each, no
  failures/skips (control 2.991s, candidate 2.576s). Correctness runtimes are not
  independent performance comparisons.
- Upstream JSON statistics/stdlib-comparison and new opt-in/limit tests: six
  roots, three race repetitions, 18 root passes (1.524s). Default, optimized
  parser/ASCII and optimized-grammar JSON variants were freshly generated with
  the candidate, rather than testing only old checked-in generated files.
- The unchanged generator plus the new test fails specifically because it
  collects default choice counters; its expression-limit test still passes.
  Retain this expected red test separately from passing candidate results.

The first language attempt lacked cached websocket v1.5.0 and was rejected
offline before tests ran. Its exact existing go.sum hashes were verified after
download into an owned temporary cache. A test-only modfile redirected that
dependency's location equally in both arms; versions and benchmark arm go.mod/
go.sum were not changed. Shared module cache was not written. Formatting the
raw generator template was also rejected by gofmt; use its declared generator,
not direct formatting of template syntax. Neither setup failure is called a win.

## Reproduction and upstream route

The [patch](pigeon-choice-statistics.patch) targets
`github.com/mna/pigeon` commit `aa1e61c16975dd7333e55c30e951bd2a0970a5ec`
(v1.3.1-0.20260627070130-aa1e61c16975), pinned by current Dang v2.1.3.
Apply it to a separate checkout of that commit. It includes the generator
template, regenerated embedded template and two portable regression tests.

From that Pigeon checkout, regenerate the embedded template using the repository
command, build the generator, and regenerate its JSON variants:

```sh
go run ./bootstrap/cmd/static_code_generator/main.go -- builder/static_code.go builder/generated_static_code.go staticCode
go build -o ./pigeon-choice-stats .
./pigeon-choice-stats -nolint -o examples/json/json.go examples/json/json.peg
./pigeon-choice-stats -nolint -optimize-parser -optimize-basic-latin -o examples/json/optimized/json.go examples/json/json.peg
./pigeon-choice-stats -nolint -optimize-grammar -o examples/json/optimized-grammar/json.go examples/json/json.peg
go test -race -count=3 -run '^(TestChoiceStatsOptInAndUndo|TestChoiceStatsKeepExpressionLimit|TestChoiceAltStatistics|TestCmpStdlib|TestZeroZero|TestForwardSlash)$' ./examples/json
```

For a clean Dang v2.1.3 checkout, use this generator in pkg/dang with the existing
`-support-left-recursion -o dang.peg.go dang.peg` flags. The resulting production
delta is 14 inserted/2 removed lines versus a regenerated control. Original
installed generated grammar-offset metadata differed from regeneration; both
arms share regenerated offsets, so those differences are not credited as a win.

Local full experiment: `/tmp/dagger-dang-choice-stats.wsM3i5zi`; frozen
`experiment.py prepare`, `compare`, `bench`, source/binary manifests and raw
results. Use a new owner for reproduction because outputs refuse overwrite.
The generator was built from its module archive using -buildvcs=false; that is
not an engine provenance bypass. Native Go's cmd/pprof was built offline because
the selected toolchain lacked its prebuilt pprof executable.

Check input SHA256: 90fde261a47bef51bac16b5d24f26f9715e7dceb498e3c420837b9b651314b0e.
Generator input SHA256: 48c95bb11c503e94cda52d61f1313f458f3813714d83acd703ed8996660f4164.
Benchmark receipt SHA256: 497ac270fa8c8a7628d6e64253fdb7f3cc05956cb0b4ad8c2a4f20ea81be4d6e.
Parity receipt SHA256: ada892b4cdff9d7dde180f0a8ec810f66b72614bd532cd84597ff0b41195915d.

This is not a turnkey public Rust demo: fixtures and full local harness are not
all published. The intended upstream path is Pigeon -> regenerate/release Dang
-> Dagger dependency update. Any adoption decision still needs a supported
current-main engine with the selected implementation and ordinary standalone
check/generate measurements with complete wcprof and correct cache invalidation.
The earlier engine experiment above is relevant prior evidence, not that gate.
No cold-install, artifact, macOS, remote-engine or new whole-CLI claim yet.
