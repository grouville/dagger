# Schema-fork reuse investigation

The prototype is rejected. The complete Go listing still takes 39.20 seconds median on the selected warm engine. No new component or full-command timing is claimed.

After extracting `evidence.tar.gz`, `testdata/attribution/` follows the selected wcprof capture into backend query and client-admission intervals. The original complete capture and goroutine snapshots remain in the scalar-getter experiment archive.

`testdata/prototype/` contains the initial clean-flag and view-tracking variants, the field-invalidation refinement, and the focused checks. Its build receipts are not benchmark results. A diagnostic engine overlay and driver were prepared but never built or run.

The final field-visibility repro uses ordinary Class field installation, with a wrapper arranging the interleaving before cloning that class. It waits for the field to be observable, not for the updater to finish. The unchanged implementation returns a clone with the field and its inferred relationship; the refinement copies the field but keeps stale membership. Both updater goroutines are joined after cloning.

The separate callback-completion repro shows a lock cycle when a custom fork callback waits for the entire update. This is an extensibility counterexample, not a reproduced hang in today's production Class cloning path.

First extract the evidence with `tar -xzf evidence.tar.gz`. To reproduce the final failure, create a disposable checkout of `ff0b029a`, copy `testdata/prototype/fork_interface_state_test.go` into `dagql/`, and run:

```sh
go test -race -count=1 -run '^TestForkInterfaceStateConcurrentFieldVisibility$' ./dagql
```

It passes unchanged. Apply `testdata/prototype/refined-server.patch`, `testdata/prototype/refined-objects.patch` and `testdata/prototype/refined-types.patch`, then repeat the same command: the clone has the new field but fails the relationship assertion. The overlays and driver receipts retain the original absolute temporary paths; patches and this test are sufficient for a fresh checkout.

Sources live under `testdata/` so Go package discovery ignores the captured variants. `MANIFEST.json` records every captured file, its source, size and SHA-256. No engine or native cache state was changed, and no upstream PR was opened.
