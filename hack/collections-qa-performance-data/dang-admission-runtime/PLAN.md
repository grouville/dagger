# Dang admission / module readiness diagnostic

Four local CLI calls only: `check -l --all` primer, profiled unchanged listing, primer, profiled unchanged listing. Each must return the exact fourteen known checks. This diagnoses fixed phase placement; the recorded wall times are not an A/B speedup comparison.

Both profiles use engine `6a82b8b3` (effective engine `38711` plus profiling only), original CLI `d685`, candidate Go module `0b12`, the original image/init and pinned SDK blobs. The isolated fixture copies the known greetings source and uses the same local `.dagger/perf-go` layout/pinned remote gomod dependency as the prior validated module experiment. Only its Go setting uses `baseAddress`; no authored app edits occur between the four commands.

The copied retained-volume lifecycle differs only in task owner and temporary-container name. Its manifest adds the original ec6 ancestry field from the recorded 38711 manifest for the existing ancestry assertion, while retaining the diagnostic manifest's exact path/hash. A new task-owned engine temporarily uses the existing owned volume; the original engine/init are never changed or started. Cleanup removes the temporary container, verifies original binaries and preserves the retained volume. Resource limits and blocking joined CLI waits are unchanged.

The environment omits Cloud configuration and credentials, uses an empty configuration directory and disables analytics. There are no production Cloud calls, no cache drops, no remote SDK update and no original workspace mutation. `dagger.lock` writes are permitted only in the isolated copy and are restored afterward. Raw stdout/stderr, wcprof data, internal identities and container metadata stay private.

Public reduction will include only fixed phase classes, counts, interval sums/unions, and relative readiness offsets for explicitly allowlisted public module aliases. Unknown aliases are counted without publishing their names. The readiness marker measures resolution completion, not publication or the moment a request is runnable; the engine's batch installation still happens after all jobs finish. No scheduling behavior changed.

Run only after parent review and an exclusive runtime slot:

```sh
python3 /tmp/collections-perf/dang-admission-runtime-v1/runtime.py --run
```

The diagnostic engine build passed. The driver was syntax-checked and dry-run only when prepared; runtime results must still establish that the new labels are emitted at the intended boundaries.
