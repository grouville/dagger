# Contextual Rust-check input experiment

This is a checkpoint of a tested module optimization, not a complete portable
benchmark distribution. See [RESULTS.md](RESULTS.md) and all paired process
timings in [pair-ba.csv](pair-ba.csv) / [pair-ab.csv](pair-ab.csv). Both include
cold failures and regressions. No timing rows were discarded.

The preceding commit contains the exact before module. This commit changes
only the check input boundary and the shared source/toolchain helpers; the
generator still receives Workspace and observes current generated paths.

## Reproduce ordinary behavior

Follow [the module instructions](../../modules/rust/README.md). In a disposable
Cargo workspace, run check/fmt/clippy/test, generate, and default check; change
a Rust library and repeat. Default check must report generated-artifact drift
without applying it. Generate must export the changed binary. Alter a generated
binary only: Rust checks should remain cached, but generator drift must still
be reported. Invalid Cargo manifests/config, toolchain selection or module
feature settings must fail; restoring inputs should reuse the old result.

The module uses standard contextual Directory arguments. Profile ordinary
commands with `dagger --profile check`; inspect `dagger.io/cache.outcome` for
Rust.check/fmt/clippy/test, not just cached Container.withExec spans. Compare
against the parent commit's module with identical engine/CLI/toolchain/cache
histories and keep complete process wall times.

## Exact recorded runs

The retained owner is `/tmp/dagger-rust-contextual-checks.lOYjM2RI`; its
build-r1/receipt, input manifests, raw telemetry, analyzer outputs and canonical
comparison JSON files carry the hashes. Existing attempt names are refused;
use unused names when rerunning this retained harness:

```sh
python3 -B run-rust-fixture.py r1 --build-attempt r1 --arm after
python3 -B analyze-smoke.py r1 --require-accepted
python3 -B run-rust-fixture.py r2 --build-attempt r1 --arm before
python3 -B analyze-smoke.py r2 --require-accepted
python3 -B summarize-pair.py r2 r1
# Reverse order for r3 before / r4 after, then:
python3 -B run-extended.py r5 --build-attempt r1 --arm after
python3 -B analyze-extended.py r5 --require-accepted
```

Analyzer nonzero exit for the rejected cold profile is expected in these
recorded runs and is retained, not converted to success. Warm profile gates
are reported independently. The test adapter [workload.py](workload.py) is the
exact extended 43-command workload. It expects the owned isolated controller's
`run_workload(ctx)` contract and pinned assets; it is not a standalone program.
The complete runner and build assets remain owner-local. Shipping the fully
portable real-repository/native demo is still an unmet goal requirement.

Each arm used a fresh owned engine and ordinary standalone CLI processes;
no listener, GC opt-out, fake cache result or omitted artifact transfer. The
common engine is current upstream ecd1ec21 plus the published Dang transport
fix and the separately tested singleton Changeset / GC reserve patches. This
module branch does not include those latter engine changes.
