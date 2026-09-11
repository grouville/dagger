# Standalone Rust generator experiment

This is a **benchmark prototype**, not the official Rust module or a general
Cargo replacement. It investigates ordinary `dagger generate -y`, including
publishing final build artifacts after real edits. The full product goal still
requires faster-than-native reusable results, near-native invalidations and
low-overhead first use.

The completed [30-pair comparison](stable-root-results.md) improves Dagger
versus Dagger, **not versus native Cargo**: the candidate still adds about
1.15–1.44 seconds on these edits. See [results](results.md) for the preceding
pilot and failed larger attempt, which remain separate and unchanged.

## Scope and ownership

- Stable Cargo >=1.91, the recorded Linux/amd64 Debian Rust image, two workspace
  packages, two executables, an rlib and a static archive. No remote/macOS or
  first-install performance claim.
- Cargo keeps mutable intermediates in its normal cache (`build.build-dir`);
  final outputs go to ordinary immutable container state. The module does not
  read a mutable cache after releasing its execution lock or invent a second
  action cache.
- The generator replaces only `target/dagger`, including obsolete outputs.
  It preserves existing ancestor permissions and checks for symlink/type
  conflicts. Final artifacts reported as Cargo-fresh are included.
- No linker/debug/optimization override, listener, resident CLI, rewritten
  project, or skipped artifact transfer. The native reference is ordinary
  Cargo via `docker exec`, with the same toolchain, flags and persistent outputs.
- The draft still rejects valid zero-final-output projects, lacks complete
  checks/tests/toolchain/platform coverage and does not support arbitrary
  projects. Do not promote it as the official module.

## Run a fresh experiment

Use Python >=3.11, GNU `ar`, Git and Docker, a matching dev CLI, two separately
built engines, and a local OTel receiver. Follow the repository's
`engine-debugging` and `telemetry-capture` skills for dev deployment and capture.
Set all three local OTel endpoints and enable live traces. Keep builds, tests,
analyzers and other workloads out of the timing window.

```sh
python3 hack/bench-rust-generators/compare-generators.py --execute \
  --dagger /absolute/path/to/dev/dagger \
  --before-engine 'docker-image://before-image?container=before&volume=before&cleanup=false' \
  --after-engine 'docker-image://after-image?container=after&volume=after&cleanup=false' \
  --before-image-id sha256:ACTUAL_BEFORE_IMAGE_ID \
  --after-image-id sha256:ACTUAL_AFTER_IMAGE_ID \
  --samples 3
```

Replace every placeholder and independently verify each engine's ID/image before
running: the optional image-ID arguments record provenance, not attestation.
Pilot first, then use 30 samples. These explicit `cleanup=false` engines measure
ordinary standalone processes with prepared engine lifecycles, **not default
engine provisioning or cold onboarding**. `--engine-readiness` defaults to
`asymmetric-or-unknown`; do not relabel it without establishing equal readiness.

Every invocation creates fresh temporary source copies, a frozen module and
unique Cargo cache keys. It retains setup and per-scenario warmup runs, excludes
warmups from statistics, rotates all six execution orders, and makes a new
observable source edit in each sample. After each timed triple it validates
Cargo target/freshness records, source hashes, final artifacts, permissions,
outside-subtree preservation and executable behavior.

Only the run's native container is automatically removed, after verifying both
its exact ID and ownership label. `--keep-native` retains it instead. Workspaces,
artifacts, failures and logs are retained; no shared engine, image, volume or
cache is pruned. Rerun the command to get new owned state, rather than deleting
a workspace or shared caches. This reset controls Cargo keys, not image/page
caches or engine readiness.

## Correctness and measurement caveats

Independent rustc incremental builds can assign different internal archive
member identifiers. Executables must be raw-byte identical. Only the two fixture
archives may use the guarded identifier-only equivalence check: GNU `ar` member
order, headers, ordinary object bytes, index and padding remain checked, and
only verified equal-length full member names plus their exact rlib link-metadata
references may differ. Raw hashes remain recorded. No files or compiler flags
are normalized. This is not a general archive equivalence library.

The baseline engine's known 755/644 ->777/666 permission defect is recorded,
never silently repaired between samples. Any unknown or candidate discrepancy
fails. This difference in output metadata history limits causal comparisons.

The post-timer `build-messages` call is a separate CLI operation. It must resolve
the same immutable action, not execute a replacement build. Cached Cargo logs
are not execution proof. Capture the complete timed and diagnostic traces,
select by exact CLI root/process boundary then whole trace ID, and require the
maintained wcprof completion/drop/replay gates. A failed or missing gate stays
failed; do not stitch another trace's marker into it.

The harness intentionally stops on mismatched evidence. Its `summary.json`
remains pending offline execution audit even after its local checks pass. The
earlier larger run documented in the results stopped when a diagnostic
unexpectedly executed another action; do not discard that failure or report
its partial samples as a completed 30-pair comparison. The separate completed
stable-root run passes 119/124 timed and 124/124 diagnostic completeness gates;
five missing markers remain rejected, including after exact-ID late rescans.

## Guard tests

```sh
python3 -m unittest discover -s hack/bench-rust-generators \
  -p test_compare_generators.py -v
```

These pure-Python tests mock the GNU `ar` and Git-setup boundaries and do not run
Docker, Cargo, Dagger or network requests. All 27 guards pass. Real archive
validation and full engine integration tests are separate. The committed module
and fixture are byte-for-byte copies of the original measured inputs. The
harness additionally hardens Git-root provenance after the failed larger run;
both versions' hashes and run boundaries remain explicit in the results.
