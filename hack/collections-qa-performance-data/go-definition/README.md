# Module definition audit

September 24, 2026. This supports the
[cold discovery analysis](../../collections-cold-cache-analysis.md#existing-sdk-work-use-moduleentrypoint).
It contains a source review and a standalone diagnostic, not an implementation
of static type loading or new full-command benchmarks.

`sdk-review.json` pins the reviewed SDK sources and records which merged engine
PRs are already included in the review checkout. The central finding is that
the existing `ModuleEntrypoint.types()` / `call()` interface supports this work;
another portable schema format is unnecessary. Static Go and Java entrypoint
prototypes already exist. Their adoption and compatibility still need testing
on the complete application.

`audit.go` locates the declarative registration expression in each existing
`dagger.gen.go`. It records its formatted size and method calls, then repeats
the in-memory parsing step 1,000 times. `results.jsonl` contains the original
results for the backend and greetings modules. Input hashes and the app revision
are recorded in the ledger.

To repeat the diagnostic from the repository root, with a checkout of the
pinned application:

```sh
go build -o /tmp/collections-definition-audit \
  ./hack/collections-qa-performance-data/go-definition/audit.go
/tmp/collections-definition-audit \
  /path/to/greetings-api/.dagger/modules/backend/dagger.gen.go \
  /path/to/greetings-api/.dagger/modules/greetings/dagger.gen.go
```

The reported microseconds exclude file I/O, Go program validation, schema
installation and any Dagger command. The diagnostic recognizes this generated
file shape only. It neither validates source freshness nor provides an
authoritative schema loader. These numbers must not be presented as discovery
latency or expected full-command savings.

No production behavior changed, and no new Dagger integration tests ran as part
of this source audit. Future entrypoint benchmarks must retain all 14 listing
rows, the custom Go base, service configuration and actual-call correctness.
