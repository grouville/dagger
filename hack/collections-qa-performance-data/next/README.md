# Follow-up discovery evidence

Read [the report](../../collections-next-performance.md) first. Every latency
sample includes CLI exit. Warm samples are serial, alternate variant order,
and exclude setup/warmup/profile invocations. `samples.json` retains commands,
working directories, exit status, output hashes and host load averages.

* `full/`: final original-collections versus full experimental stack, five warm
  samples per variant, real edits, complete expected output and CLI profiles.
* `split-imports/`: isolated Node SDK packaging experiment, patch, five warm
  samples, edits, actual method calls and cold failures.
* `go-existence/`: committed Go patch, scaling samples and 11 passing module
  checks. `greetings/` records the inconclusive small-app comparison.
* `node-cache/`, `cjs/`, `bun/`: separate alternatives, each with its own control.
* `import-markers.json`: diagnostic timings inside TypeScript processes, not
  end-to-end latency samples. The wrapper changes import ordering deliberately.
* `manifest.json`: source pins, binary hashes, SDK bundle hashes and scope.

The drivers are exact laboratory scripts, not a standalone environment
installer. They reference `/tmp/collections-perf` workspaces, prepared engines,
local checkouts of dagger/go, the committed CLI, the original CLI and the
isolated syntax-cache engine. See the preceding reports for their provenance.
Use `hack/bench-artifact-discovery.py` for independent repetitions and wcprof
capture against a prepared engine. Do not run builds/tests concurrently with
latency measurements.

To review the new Go change, apply `go-existence/go-module.patch` with `git am`
to dagger/go at `1784ff37eb3dd1aacab7aaff91b1d86e311cc8de`.
The SDK patch applies to greetings-api at
`14d684fccf75a137de96f3f0c7eb8c6dafef2d3e`; it changes generated files and is
only a prototype, not a replacement for an SDK generator fix.

Binary profiles remain in the laboratory directories recorded by the manifest;
the checked-in summaries preserve the operation counts and findings. Cold
failures are retained in `split-imports/cold-attempts.json`; failed runs must
not be used as cold-performance measurements. The failed CommonJS setup is
retained locally under `ts-cache/cjs/results-failed-import-meta`.
