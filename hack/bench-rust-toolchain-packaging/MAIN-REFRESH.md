# Current-main refresh and rejected warm-start hypotheses

2026-09-14. **Provenance/diagnostic checkpoint, not a new Rust speedup.**
The [relay full-flow scorecard](RELAY.md) remains the latest validated ordinary
CLI comparison. Every median there still loses native Cargo. The cold/warm
performance goal is unmet; library microbenchmarks below do not replace it.

## Stack and upstream base

Upstream main was rechecked at `c305ed3757e587045c3c51b5d717f7d64db77377`.
Nine perf23–29 commits were replayed, without changing their patches or messages,
onto that base in `perf/rust-30-main-refresh`. All nine `git range-diff` entries
are equal and all nine SSH signatures verify. Old fork branches are preserved;
no force push or PR. The original dirty experiment workspace was not modified.

| Original commit | Rebased commit | Scope |
| --- | --- | --- |
| bbd67d9db | 6a7f01b1e | Final-session telemetry drain fix |
| 5b8b036f8 | d7a3dccd3 | Successful module URL routing persistence |
| fcd2c00ae | 60758837b | Cold pre-sync attribution |
| db293a369 | 6b22f3f44 | Normal cold writeback attribution |
| db870fc60 | b11719d21 | Mixed writeback-ahead evaluation |
| 4481a4d96 | 541b813cd | Prepared OCI packaging evaluation |
| a3f366770 | e8b8dffb5 | Hashing/pipe CPU attribution |
| 24bf88c96 | 1617b15f9 | Bounded-relay full-flow evaluation |
| e778847d7 | 04a0b2913 | Kernel fsync/off-CPU attribution |

The upstream delta from `7c35e6274737acff0f6bd76614abb5e04efa7d12` is 21
workspace/SDK configuration and generated-code files, not engine/client or root
Go dependency changes. Nevertheless, rebase is not rebuild: historical engine
562e/7a27 and CLI6a5 results remain measurements of their original frozen inputs.
This public stack contains two runtime fixes and diagnostic documentation, not
the entire older unpublished engine/CLI/containerd experimental bundle.

Focused rebased correctness validation passes:

- Core URL/lock tests: 25 roots, three repetitions each, 75 root passes,
  zero failures/skips, `-race`, package runtime 2.496s.
- Telemetry completion tests: six roots, three repetitions each, 18 root passes,
  zero failures/skips, `-race`, package runtime 1.415s.

Exact Go test selectors (both `-mod=readonly -p=2 -race -count=3 -v -timeout=90s`):

```text
./core
^(TestDaggerGet|TestResolveDaggerGet|TestSourceURLWithVersion|TestUpdateVanityURL|TestVanityURLResolution|TestUpdateWorkspaceLockIgnoresUnsupported)

./engine/server
^(TestMainShutdownKeepsTelemetryUntilSessionComplete|TestMainTelemetrySSEDrainsFinalCarrier|TestMainTelemetryDoesNotWaitForContainerRelease|TestMainTelemetryReconnectWaitsForLastDisconnect|TestMainTelemetryWaitsForAllProviderShutdown|TestNestedShutdownStillClosesOwnTelemetry)$
```

These are focused correctness runs, not new supported engine integration or
end-to-end performance results. Local owner:
`/tmp/dagger-warm-current-main.UqZkIcLi`.

The initial core attempt failed because the sandbox disallowed the local
httptest HTTPS listener. The unchanged retry requested scoped socket access;
no network dependency downloads, global settings or test gates were changed.
The first signing attempt likewise lacked sandbox access to the existing SSH
agent; scoped signing access completed the rebase without reading a private key.

## Warm-start experiments, not accepted runtime changes

Pinned library: the current Dagger dependency `github.com/vito/dang/v2 v2.1.3`.
Go 1.26.8, GOMAXPROCS=2, one heavy process at a time, file I/O outside timing.

### Bind only query-root value wrappers

Scope: avoid constructing then discarding non-query object field wrappers.
Type preparation, mutation calls and object-method selection were left intact.
Both arms passed focused race tests three times. Six alternating AB/BA pairs
on the checked-in Dagger introspection fixture yielded:

| Library phase | Control median | Candidate median | Median paired saving | Favorable pairs |
| --- | ---: | ---: | ---: | ---: |
| Root value binding | 90.952 us | 75.8615 us | 14.564 us | 6/6 |
| Full import preparation | 327.740 us | 309.920 us | 17.8265 us | 6/6 |

The full-import range is 2.794–34.713 us. This is not the actual captured Rust
runtime schema and is far too small to explain 400–600 ms ordinary warm overhead.
No engine build or Rust gain is claimed. Repro owner:
`/tmp/dagger-dang-query-bind.ChP9Aobz`, `experiment.py --prepare`, then `--bench`.
The first preparation rejected a mistyped binary pin before running tests; the
corrected pin and successful retry are retained separately.

### Existing parser options

Memoize(true) was slower in one fixed-order pilot: check-module parse
10.999 -> 16.847 ms; generator parse 49.002 -> 69.021 ms, with roughly 4.4 times
the allocated bytes. This is a rejection diagnostic, not randomized E2E evidence.
The first AST comparator was invalid: non-nil function fields fail DeepEqual
even across two default parses. Its failures are retained, not called library
regressions or silently converted to correctness passes.

### Existing generator ASCII lookup flag

Pinned Pigeon `v1.3.1-0.20260627070130-aa1e61c16975`, original left-recursion flag
versus that same flag plus `-optimize-basic-latin`. The regenerated control and
candidate differ only by generated ASCII tables and the narrow matcher fast
path. Six alternating pairs reject it as a performance candidate:

| Parse | Control median | ASCII median | Median paired saving | Favorable pairs |
| --- | ---: | ---: | ---: | ---: |
| Rust check module | 10.437620 ms | 10.639869 ms | -0.193146 ms | 0/6 |
| Rust generator module | 47.314828 ms | 47.446899 ms | -0.167533 ms | 3/6 |

Existing format/highlight tests passed in both arms. Structural AST/location,
comment, raw/recovered error and formatted-output snapshots matched across 751
entries. Function symbolic names are included but are not semantic proof; JSON
string normalization means malformed-output byte preservation is not fully
validated. No engine/semantic/platform acceptance is claimed. Broader grammar
optimization was generated separately but quarantined because public alternate
entrypoints and diagnostics can change; it was never benchmarked or accepted.

Regenerating the installed baseline changed only grammar position offset numbers
(five bytes from grammar line 1124). Both comparison arms share regenerated
metadata; no byte-for-byte reproduction of the installed generated file is
claimed. The pinned downloaded generator needed `-buildvcs=false` because its
module archive has no Git checkout, not to bypass engine provenance validation.

Repro owners: `/tmp/dagger-dang-parser-options.HkQ03TsD` and
`/tmp/dagger-dang-parser-codegen.WPeewNbN`; the latter runs `experiment.py prepare`,
`compare`, then `bench`. Full source/binary pins, failures, snapshots and all
sample records remain local. Use a new owner because results refuse overwrite.

## What is not claimed

No new wcprof/Rust CLI speedup, complete-install result, artifact result, macOS/
remote validation, maintainer approval or new default UX. No parser caches,
resident process, egraph identity, Cargo cache key, GC or durability changes.
No raw/private profiles, analyzer binaries, credentials or experimental images
are published. The next accepted performance change still needs a supported
engine build and ordinary full-flow A/B, with complete wcprof and correct work.
