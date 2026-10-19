# fix(dagql): keep field overrides independent after a class fork

While investigating schema work during Go test collection listing, I found that overriding a field in a forked class could change the parent class's definition.

A fork copies the field map, but the parent and fork still share the arrays storing each field's history. If an array has spare space, both can append into the same slot. Adding a fourth definition to the fork then overwrites the fourth definition previously added to the parent.

Limit the history's capacity before appending in `Install` and `Extend`. The append then gets separate storage, while existing history entries can stay shared.

The cost is an allocation when an override would previously have reused spare capacity. That separation is needed to keep the definitions independent; reading or forking a class without adding an override does not incur it. This is a correctness fix, with no claimed listing speedup.

### Reproducing

The regression installs three versions of a field, forks the class, and adds a different fourth version to each. It checks both `Install` and `Extend`. On main `80699ac67a`, the parent returns the fork's definition; with this fix, each returns its own.

```sh
go test -race -count=1 ./dagql -run '^TestClassForkHistoryIsolation$'
```

To run the rest of the DagQL tests as well:

```sh
go test -race -count=1 ./dagql
```
