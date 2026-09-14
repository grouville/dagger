# Reproduce the contextual-generator experiment

This package checkpoints the compared workload and evidence, not the final
portable public Rust demo. The source/input boundary change is in modules/rust.

The maintained wcprof analyzer and isolated controller used here are local
artifacts recorded by hash in the common provenance and runner manifests.
Do not substitute a listener or skip automatic provisioning when reproducing.
Use the owner scripts (one heavy job at a time, fresh attempt names):

```sh
python3 -B /tmp/dagger-rust-build-output.vrRYC6gW/run.py r7 --build-attempt r1 --arm before
python3 -B /tmp/dagger-rust-build-output.vrRYC6gW/analyze.py r7 --require-accepted
python3 -B /tmp/dagger-rust-build-output.vrRYC6gW/run-contextual.py r8 --build-attempt r1 --arm contextual
python3 -B /tmp/dagger-rust-build-output.vrRYC6gW/analyze-contextual.py r8 --require-accepted
python3 -B /tmp/dagger-rust-build-output.vrRYC6gW/summarize-pair.py r7 r8
```

Analysis exits nonzero if any gate fails, after retaining diagnostics. Existing
runs fail cold replay; never silently convert that into a full pass. The before
and candidate modules, source/asset hashes, engine tarball and CLI are guarded by
the owner scripts. The controller creates a new private daemon per run; host
containers/volumes are preserved. No host-wide prune/reset is used.

The workload files here are the exact captured assets. The candidate adds output
correctness probes after the common 59-command measured prefix. Fresh fixture
names provide the cache reset, not reused exact-source hits across arms.

See [results and limitations](RESULTS.md), raw CSVs and evidence.json. The next
product-validation step is an equivalent unprofiled pinned-real-repo/native
matrix, not claiming this tiny diagnostic is the final demo.
