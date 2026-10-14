# Validate Cargo configuration with native snapshots

The isolated module branch records the digest of its filtered Cargo
configuration directory when capturing a plan. Edited builds compare that
native digest instead of exporting manifests, lockfiles, Cargo configuration
and toolchain files into the Go helper. Capture still performs the original
configuration read once. Existing plans without the new field keep that path.

The original content/mode configuration digest stays in compiler identities.
The added native digest is validation metadata and does not alter result or
incremental-seed keys. Both validation paths still check supported compiler
flags, derive dependencies and reject cycles. Source and seed directories
remain execution inputs; this adds no ignored cache-key input or shared lock.

## Correctness

Focused model, replay, worker and wrapper tests pass. The actual module passes
cold compilation, the configured normal check, a Directory edit with 3/4
hits, reversion with 4/4 hits, and transfer to a new engine with 4/4 hits
followed by a new edit with 3/4 hits.

Actual host changes to the manifest, lockfile, Cargo config, toolchain config
and configuration-file permissions are rejected without publishing metadata.
Restoring the configuration recovers 4/4 hits. The integration driver's writer
also covers those configuration changes with native Directory inputs.

The existing path-only boundary remains: automatic plan/cache discovery and
support for registry dependencies, build scripts, procedural macros and tests
are still required. Directory mutation checks use the scoped imported-hash
engine fix already described in the module report.

## Edited-command measurements

Both series use five alternating pairs per scenario on the actual 102-action
module, independent source trees, Cargo targets and native histories, unique
edits, four preparation rounds, and a failed-compilation publication check.
Telemetry stays enabled to the local receiver; wcprof is off during timing.
All 20 Cargo rebuild sets in each series match 2 crates for leaf edits and
102 for shared edits. Native hit counts also match 100/102 and 0/102.

| Complete-command median | Initial control | Native validation |
| --- | ---: | ---: |
| Leaf | 0.996 s | 0.853 s |
| Leaf Cargo | 0.087 s | 0.085 s |
| Shared | 1.477 s | 1.396 s |
| Shared Cargo | 0.473 s | 0.476 s |

All ten pairs improve initially. Compiler plans match after excluding capture
diagnostics and native validation metadata. However, the variants use different
helper builds and separately prepared histories. Maximum CPU/I/O pressure is
21.8%/20.8%.

The confirmation uses the same module code, worker binary, captured plan and
initial snapshots. Removing only the native validation field exercises the
legacy export path; keeping it exercises the native digest path.

| Complete-command median | Export validation | Native validation |
| --- | ---: | ---: |
| Leaf | 0.956 s | 0.988 s |
| Leaf Cargo | 0.089 s | 0.087 s |
| Shared | 1.519 s | 1.481 s |
| Shared Cargo | 0.474 s | 0.479 s |

Two of five leaf pairs and four of five shared pairs improve. Retain every
sample, including the 2.324-second control shared edit and 0.862-second Cargo
edit. Maximum CPU/I/O pressure is 21.2%/24.9%. The confirmation does not prove
the initial 142 ms leaf benefit or a general complete-command improvement.

All eight captures have zero dropped events. Configuration export disappears
from candidate profiles, saving a directly recorded 14–17 ms operation in
the confirmation, but filtering still copies configuration files. The new
digest and variable surrounding work prevent attributing that entire interval
to a net command saving. Candidate profiles include snapshot-lease lock waits
of 44 ms for a leaf edit and 183 ms for a shared edit; the latter also has a
1.29-second compiler workload. These are investigation targets, not evidence
that removing a lock is safe or that native validation caused the waits.

Keep this as a separate experiment before selecting it in the main native
backend. Branch: [experiment/native-configuration-snapshots](https://github.com/grouville/dagger-rust/tree/experiment/native-configuration-snapshots).
Artifacts under `/tmp/rust-cache-sipsma-review`: `native-config-*`,
`module-native-102-config-snapshots`, `module-native-102-config-confirmation`,
and their `measure_native_102_config_*.py` local reproduction harnesses.
