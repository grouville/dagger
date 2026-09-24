# Archive parent-path experiment

See the [report](../../collections-extraction-parent-performance.md) for scope,
results and the decision to leave this prototype disabled.

* `parent-cache.patch`: isolated containerd v2.2.5 source and test changes.
* `bench.py`: fresh-volume imports and complete listings, including the corrected
  `balanced` mode with the same shutdown step after every sample.
* `warm.py` and `invalidate.py`: alternating warm runs and real source edits.
* `summary.json`: all twelve cold samples with profile and host-pressure counts.
* Sample directories: command results, exact output, phase timings, timelines,
  wcprof analysis and compact host samples.
* `warm.json`, `edits.json`, `edit-outputs.json`: warm results and verified edits.
* `root-tests.log`: complete archive test run with root-only tests enabled.
* `provenance.json`: revisions and hashes of large raw artifacts kept in the lab.

The scripts use the same `/tmp/collections-perf` layout as the earlier reports.
Apply the patch to an isolated copy of containerd v2.2.5, then add a replacement
for that copy to a copy of the experimental engine modfile. The candidate build
used:

```sh
CGO_ENABLED=0 go build -buildvcs=false \
  -modfile=/tmp/collections-perf/tar-parent-cache/engine.mod \
  -overlay=/tmp/collections-perf/prebuilt-ts-sdk/overlay.json \
  -o /tmp/collections-perf/tar-parent-cache/engine ./cmd/engine
```

It otherwise uses the previous experimental stack unchanged. The benchmark
scripts assert that their engine names and volumes do not already exist;
choose fresh names and ports for another run. Do not reuse one writable volume
between concurrent engines. The first full series intentionally remains
reproducible with its recorded lifecycle imbalance; use `balanced` for the
corrected protocol.
