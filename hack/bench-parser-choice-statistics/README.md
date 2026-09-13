# Opt-in parser choice statistics: a small, mixed Rust-loop pilot

Status: an upstream-library performance candidate, **not an activated Dagger
dependency update or a general Rust-loop win**. The complete goal remains unmet.
This checkpoint adds inert patches, tests and evidence. It does not ship the
experiment's local `replace` directive or change Dagger's cache model.

## Context and change

An aligned engine CPU profile over 24 standalone, prepared exact checks exposed
default Pigeon parser bookkeeping. The 20-second capture contains 9.07 CPU-seconds
of samples, including 1.39 seconds attributed to parser recursion and 0.32 seconds
cumulative under `incChoiceAltCnt` (0.21 seconds under `fmt.Sprintf`). These nested
numbers overlap. They are not removable CLI wall time or child-process CPU.
wcprof validated 25 complete exact captures, including the preceding reference.
The diagnostic controller's timeout-enabled process wait introduces polling
rounding; its elapsed CLI figures are not headline latency measurements.

The generated parser was building per-rule choice-counter maps and formatting
counter labels even when nobody requested `Statistics`. The proposed generator
change keeps the default `*Stats` and expression counting, but leaves the choice
map nil and returns before formatting when choice counting is disabled. Explicit
`Statistics` still initializes and accumulates counters. A private restore option
preserves the exact pointer, map-enabled state and no-match label through undo,
redo and switching between statistics objects.

There is no parsed-AST cache, shared mutable interpreter state, skipped source
sync, hidden listener, session reuse, new lease, cache-key change or omitted Cargo
work. `MaxExpressions`, `Memoize`, left recursion, recovery and the public parser
options remain available; this does not enable `-optimize-parser` for Dang.

The deliberately observable behavior change is that same-package custom options
inspecting default `p.Stats.ChoiceAltCnt` now see nil instead of implicit counters.
`Statistics(nil, ...)` already panics; this does not broaden that contract.

## Measured results

Linux/amd64, Go 1.26.8, pinned 87-line Rust check module, three independent process
pairs AB/BA/AB. Both parser binaries use the default *without* explicit Statistics.
Per-parse savings: **2.887 ms paired median**, range **2.508–2.982 ms**, 3/3 pairs.
Allocations drop by about **30,016 per parse**, with about **444,608 fewer bytes**.
These are microbenchmarks, not savings per Dagger invocation.

The subsequent real ripgrep comparison uses six fresh, independent engine/Cargo
states, ordered ABBAAB. Within-run repeated edits are summarized before forming
the three pairs. The CLI, module, grammar, toolchain and engine parent match;
only generated parser statistics differs between treatments.

Positive savings mean candidate B was faster. All times below are milliseconds.

| Flow | Paired CLI saving, median [min, max] | Favorable pairs | Candidate Dagger median | Native median | Paired native overhead median |
| --- | ---: | ---: | ---: | ---: | ---: |
| First check, engine image cache empty¹ | +117.7 [-924.9, +166.3] | 2/3 | 17,628.5 | 6,528.9 | +10,889.2 |
| Engine provision + first check¹ | +93.1 [-955.6, +162.6] | 2/3 | 17,880.4 | 6,528.9 | +11,104.3 |
| Unchanged check | +13.5 [+1.1, +39.9] | 3/3 | 425.8 | 117.9 | +307.9 |
| Application edit | **-4.0 [-4.6, -2.0]** | **0/3** | 812.6 | 293.3 | +503.3 |
| Workspace-library edit | +30.5 [+18.9, +73.1] | 3/3 | 940.8 | 459.0 | +485.3 |
| bstr 1.12.0 → 1.13.0¹ | **-10.5 [-82.7, +51.3]** | **1/3** | 2,164.7 | 1,657.2 | +466.6 |
| Unchanged after upgrade | +19.8 [-30.5, +22.3] | 2/3 | 415.0 | 147.4 | +278.2 |

¹ These timings include wcprof instrumentation. Other timed warm commands omit
`--profile`, but **all still export OTLP to a local receiver**. Native means
Cargo through `docker exec` in the matched preinstalled Rust image, not bare-host
Cargo. Paired overhead is a median of differences, so it need not equal the
displayed marginal medians' difference. The JSON retains individual measurements,
ratios, ranges and native-normalized deltas; no outliers are discarded.

The application result cannot be called a CLI win just because its
native-normalized overhead improves by 6.6 ms. Likewise exact-hit normalized
overhead changes by -0.4 ms, despite the positive raw CLI median. All three
native-normalized cold overheads worsen (median +278 ms for first check and
+303 ms including provisioning); **there is no demonstrated causal cold win**.
Network, Cargo and scheduling variation are not separated by three pairs.

The separate profiled exact samples show `ModuleSource.asModule` self-time
reductions of 6.3/23.9/4.2 ms, and `Rust.check` self-time reductions of
4.1/2.0/0.3 ms. They support a small module-loading effect, not addition of phase
savings to the CLI table. Warm replay drift is -0.0 to -0.1%; cold replay drift
is -4.6 to -5.0%. Structural completeness does not justify precise cold what-ifs.

All representative flows still lose to native. These engines **exclude** the
separate stream/hash, codec and parsed-source-reuse experiments. Do not compare
these absolute cold times with those other engine compositions or add their gains.

## Correctness and boundaries

- 36/36 complete wcprof captures pass declared/received span, structural, execution,
  affected-package and complete-image-byte gates; no rejected capture.
- All 36 ordinary warm crate audits agree with native: an application edit checks
  only ripgrep; the selected library edit checks grep, grep-printer and ripgrep.
  The real bstr upgrade selects 1.13.0, not 1.12.0, and leaves unrelated memchr cached.
- 18/18 cache snapshots parse successfully. That alone does not prove cache parity;
  actual exec/package gates provide the stronger evidence. Exact and restart-exact
  profiles have no actual Cargo execution or image transfer.
- Compile failure, repair, failing-source revisit and cached repair are exercised.
  The later application diagnostic follows that recovery history and checks three
  crates; it is not relabeled as the ordinary one-crate timed edit.
- All cold runs download and read the same two complete compressed Rust layers,
  totaling 316,873,658 bytes. The direct-origin registry configuration is diagnostic,
  not a claim about the default dev-engine mirror or complete installation.
- 480 unchanged Dang files have enabled/disabled AST, errors and source-location
  parity, with memoization and expression-limit checks; race/count3 passes.
  The initial raw `reflect.DeepEqual` comparator failed on static operator function
  values even for identical input. The corrected type-specific comparator keeps
  every AST field and has its own changed-operator/function regression checks.
- Pigeon builder, JSON normal/optimized/optimized-grammar and left-recursion paths
  pass race/count3. Generic JSON default/undo/redo/switch/accumulation/parity tests
  pass race/count10. The original generated JSON parser fails the intended default
  and restore negative controls. Existing exact choice-count expectations still pass.
- The published patch was reapplied to fresh pinned source copies, regenerated
  template/parser bytes matched the measured candidate exactly, and generic JSON
  plus the relocated 480-file Dang race suite passed again. A single-iteration
  benchmark checked the portable fixture input; its timing is not new evidence.
  The copied repro controller corrects only a comment that incorrectly called
  that final non-race single iteration race-instrumented; commands are unchanged.
- The supported current-main engine-dev Dang integration selection passes, followed
  by two local dev deployments and smoke queries. See recorded command identities.

The six benchmark-owned container/cache groups were independently verified absent
after cleanup; captures and workspaces remain. The receiver exited normally after
termination. Existing user trees, engines and cache volumes were not reset.

This is a minimal **check fixture**, not the completed official module. There is
no new artifact-export, fmt, Clippy, test-command, build.rs/features matrix,
concurrent-invocation, macOS, remote-engine or complete-installation score here.
Docker, CLI, engine image, native Rust image and local module are preinstalled.
Host page/CDN caches are not purged; native follows Dagger for the initial check.

## Source identities and upstream path

The experiment parent is `503d3410ef3df63fa6bc7a55c5c2453c4951c2c2`: the prior
26-commit experimental stack rebased onto upstream main
`7c35e6274737acff0f6bd76614abb5e04efa7d12`. The rebase was conflict-free;
these scratch rebased ancestors are unsigned. Publishing this new checkpoint
branch preserves them; it does **not** rewrite or certify every older fork branch.
Historical commit bodies and the [stack index](../bench-rust-loop/stack-index.md)
remain historical. Upstream main was rechecked before publication and still 7c35.
Both runtime variants were actually rebuilt on this base. The identical external
CLI comes from `experiment/client-http-preconnect` commit
`47a552be8acb2e76768f74d0cb4c85d843cfc218`, also based on 7c35.

Pigeon: `github.com/mna/pigeon@v1.3.1-0.20260627070130-aa1e61c16975`.
Dang: `github.com/vito/dang/v2@v2.1.3`.
The patch changes Pigeon's source template **and regenerated template**, plus
generic tests. Dang's parser was then regenerated with the same grammar and
`-support-left-recursion` flag. Both experimental engines use identical local Dang
wiring; no permanent vendored module or `replace` is proposed for Dagger.

The shipping sequence is: Pigeon change/release → pin that tool release in Dang
and regenerate/release Dang → update Dagger's Dang dependency. The prototype
Dang go.mod still names the original Pigeon version; ordinary regeneration with
that pin would revert the optimization. Explicit use of the candidate generator
is experiment wiring, not a substitute for the eventual tool-pin update.
No maintainer approval or external-library PR is claimed.

Stock pinned Pigeon regeneration differs from Dang's released generated file only
in grammar `offset:` positions. Both experiment sides regenerate the same input,
so the candidate/control diff contains only statistics changes. After normalizing
`offset: [0-9]+` to `offset: 0`, released and regenerated control both hash to
`832b46817fd1b217f814ff2966a1a864c915b974297518af93ee126108fbf5a4`.
Do not hand-edit the generated parser to hide that reproducible offset churn.

## Reproduce

The [Pigeon patch](patches/pigeon.patch) applies at the pinned Pigeon revision.
Use owned writable copies, not the shared Go module cache. From that copy:

```sh
git apply /absolute/path/to/patches/pigeon.patch
(cd builder && go generate static_code.go)
go build -buildvcs=false -o /absolute/path/to/pigeon-candidate .
```

Build an unmodified pinned generator separately for the control. In an owned Dang
v2.1.3 copy, regenerate both parser outputs from the same `pkg/dang/dang.peg`:

```sh
cd pkg/dang
/absolute/path/to/pigeon-control -support-left-recursion -o /absolute/path/to/control.dang.peg.go dang.peg
/absolute/path/to/pigeon-candidate -support-left-recursion -o dang.peg.go dang.peg
```

Copy `patches/dang-choice-statistics_test.go.txt` into that package as
`choice_statistics_test.go`. Its only adaptation from the measured test is that
the benchmark reads `DAGGER_RUST_PARSE_FIXTURE` instead of a fixed local path.
Point it at the included `fixtures/rust-module.dang` (SHA256
`f6e119c3b7be439df46a6ea9b74c368126751e0a141b2e5ebb699a4b0f0681f1`).
Run `go test -race -count=3 ./pkg/dang -run '^TestChoiceStatistics' -v` from
the Dang root. Build two test binaries with identical flags, using Go's overlay
JSON to substitute only the control generated parser for the A binary. Run them
sequentially ABBAAB with:

```sh
./dang-variant.test -test.run='^$' \
  -test.bench='^BenchmarkRustModuleParseChoiceStatistics$/^counted=false$' \
  -test.benchtime=1s -test.count=1 -test.benchmem
```

The [historical controllers](controllers) retain exact build, benchmark and
analysis commands, flags, source/image hashes and cleanup ownership gates. They
contain original local paths and need explicit path/output/identity adaptation
on another machine; they are **not** advertised as a portable one-command demo.
The supported build helper and cold-flow adapter are included. Use the same engine
parent on both sides, the same local replacement wiring, and verify that the
generated parser is the sole production difference before timing. Preserve all
cache/byte/crate/error/restart gates when adapting the controllers.

Raw telemetry, CPU profiles, binaries and the private wcprof analyzer remain
local. Their hashes and compact validation are included; no analyzer code or
public OCI image is uploaded. No PR is opened by this checkpoint.
