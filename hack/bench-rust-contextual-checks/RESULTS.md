# Contextual inputs: two opposite-order full-module pilots

2026-09-14. Module-only candidate on the same current-main comparison engine.
Two independent pairs: B/A (r1 after, r2 before), then A/B (r3 before, r4 after).
Six loop samples per flow per arm in each pair. All commands are profiled.
These are tiny-workspace diagnostics, not native Cargo or real-repo headlines.

## Whole-process medians, milliseconds

| Flow | Pair 1 before | Pair 1 after | Saving | Pair 2 before | Pair 2 after | Saving |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Unchanged default check | 1024.2 | 761.7 | 262.5 | 910.2 | 781.5 | 128.7 |
| Novel library edit + default check | 2185.5 | 1979.6 | 205.9 | 1988.4 | 1921.8 | 66.6 |
| Follow-up cached-build artifact export | 1038.5 | 866.5 | 172.0 | 853.3 | 855.6 | -2.3 |

Unchanged-check reduction repeats (25.6% /14.1%). Edit-check medians improve
9.4% /3.3%, but this is a small two-pair sample. The apparent artifact-export
gain does not repeat; do not call that an established improvement. Keep the
full vectors, maxima and individual regressions in the canonical JSON reports.

The sampled unchanged maximum falls 1168.0->882.8ms in pair1 and 927.8->811.4ms
in pair2. Edited maximum falls 2390.6->2074.1ms and 2041.1->1940.1ms. No >5s
default-check stalls in either arm; the transport fix is common, not re-counted.

## Mechanism / correctness

All four checks in B hit the normal function cache for every unchanged loop:
48/48 selections across the two after runs. All checks execute on novel edits;
each edited default check runs exactly check/fmt/clippy/test/build, with no
repeated toolchain setup. Both before runs re-evaluate those four functions on
unchanged inputs even though Cargo itself is cached.

All runtime assertions pass for all four runs: failure/repair, immutable old
snapshot revisits, binary behavior after each edit, generator drift without
host mutation, lockfile output, and unrelated file/mode preservation.
All **128 warm wcprof profiles** pass completeness, no-drops, structure, and
absolute replay drift <=2%. Every cold profile fails replay accuracy. Overall
full-smoke acceptance remains false; these reports do not erase failed gates.

## Retained limits and regressions

- Cold first-check process times: r1 19.875s, r2 25.283s, r3 23.539s, r4 24.504s.
  No cold speedup attribution; image delivery and the original goal remain
  unresolved. These exclude full installation of CLI/module/Docker.
- First Clippy setup is slower in both after runs: +214.4ms /+204.9ms. The
  rustup component-add subprocess accounts for +207.6ms /+131.4ms, with session
  and execution waits contributing in pair2. Same command/input intent does
  not prove this is noise; retain and investigate before broad promotion.
- No unchanged native Cargo comparison, no measured external dependency
  upgrade, no unprofiled headline, macOS or remote-engine validation here.
- Extended r5 correctness probes for generated-output-only changes, Cargo
  manifest/config, toolchain and module settings pass, with all 42 warm wcprof
  quality gates passing. Invalid inputs execute and fail; repaired snapshots
  hit the function cache. Target-only drift keeps all four Rust checks cached
  while detecting the changed artifact; regeneration restores exact bytes.
  Invalid inputs test cache-key coverage, not actual dependency/toolchain
  upgrades or their performance. The r5 cold profile fails replay (-3.6%).

## Provenance

Module before SHA256 8408ad0afdccaddda6fab063cc67c8fe2609da9ae4e8a9e36f078d255b490a2a.
Module after SHA256 f995374afcfda19442427e1160a12569064a340d2c1cbc5b4cd4a650460ed45a.
Build/source receipts and input manifests retain exact engine/CLI/controller
hashes. Same engine and CLI in both arms, ordinary standalone UX, isolated
fresh engines, unchanged host inventory, and no listener. There are no per-arm
GC/cache adjustments: both arms use the same separately recorded patched
engine, including the common GC-reserve fix. This is not unpatched-main proof.
See [engine-provenance.json](engine-provenance.json) for exact source and binary
hashes of those common dependencies.

Canonical pair1 comparison: comparison-r2-r1.json, SHA256
43b27a73dd87b75906f3fd2cd9095800a286811d0d67c4d1f92aaf7f0d8f5c37.
Canonical pair2 comparison: comparison-r3-r4.json, SHA256
9b44519f6aa6c494ba0de5d6704f9abb2bcbe043a77de018e2e1b8d19aefd6cf.
The module is checkpointed separately on perf/rust-contextual-check-inputs; no
cold or all-platform promotion is implied. The published transport fix remains
perf/dang-transport-shutdown.
