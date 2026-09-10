# Pinned ripgrep check: 2026-09-10

Revision: 3fce3b5bb0236da2df6d99672afb8a719642eca7. Rust image, flags, working
directory and target path match. Five samples, alternating native/Dagger order;
all samples retained. Native includes docker exec. Dagger uses the deferred-OAuth
CLI, separate sessions, standard LOCKED target/source caches, rsync checksum
source reconciliation and persistent Cargo registry/Git caches. Downloads and
targets are primed on both sides; this is not a cold-start result.

| Scenario | Native median ms | Dagger median ms | Overhead ms |
| --- | ---: | ---: | ---: |
| Exact | 141.54 | 851.97 | 710.43 |
| Application edit | 326.05 | 1191.76 | 865.71 |
| Workspace-library edit | 491.43 | 1534.76 | 1043.33 |

The faster-than-native exact-hit target and preferred 500 ms edit overhead are
not achieved. These are checks only, not build/artifact or dependency-version
change results. No claim about host-native Cargo, remote engines or macOS.

Correctness/incrementality evidence:

- Application edits change ripgrep's version output string; Cargo's rebuilt
  package is ripgrep on both sides.
- Library edits change grep-printer's omitted-context string; both sides rebuild
  grep-printer, grep, ripgrep. The rebuilt-package lists match for all ten edited
  samples. They do not rebuild all registry dependencies or workspace crates.
- A compile error is rejected, repair succeeds, revisiting the older rejected
  content still fails with 101, and returning to repaired content succeeds.
- Diagnostic check-log retrieval is outside timers and reads the evaluated
  action's stderr. Exact-hit logs describe the cached producer, so they must not
  be interpreted as fresh compiler executions.

Separate library-repair wcprof sample: 701.1 ms recorded span, 524.4 ms inside
the rsync/Cargo shell command, 411 ops, no open ops or dropped events. Module
loading self-time is 33.9 ms; four host directory resolvers total 23.3 ms.
The whole CLI still costs appreciably more than the recorded engine span.
Use full-lifecycle telemetry to locate that gap; do not add nested self-time
rows together or treat counterfactual estimates as measured savings.

Raw paired timings: `ripgrep-check-timings.csv`. Full local logs and native
wcprof captures: `/tmp/dagger-rust-loop-_039uuwv`. Engine baseline 59a9b904d1;
candidate CLI SHA-256 5507e7e555a18847e3a0d2d413651f640d1fe42703f0151af7ae7dad72928248.
