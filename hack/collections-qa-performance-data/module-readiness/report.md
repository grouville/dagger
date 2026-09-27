The collection loader has a real scheduling opportunity, but this profile bounds it to **167–193ms**, not the entire static catalog phase.

| Boundary relative to catalog start | Warm diagnostic | Fresh comment-edit diagnostic |
| --- | ---: | ---: |
| Backend module resolved | 232.26ms | 192.44ms |
| Go module resolved | 587.53ms | 528.70ms |
| Final module resolved (TypeScript SDK) | 740.90ms | 667.95ms |
| Static catalog returned | 780.56ms | 695.78ms |
| Go + backend ready → catalog returned | **193.03ms** | **167.07ms** |
| Catalog returned → expansion began | 94.61ms | 37.14ms |
| Collection expansion duration | 873.86ms | 814.72ms |

All nine module-name markers are descendants of the catalog operation and belong to its client. Their completion means the module definition was resolved; batch arbitration and schema publication still occur afterward. Every marker completed successfully, and both profiles dropped zero events. The ninth module, Playwright, started as soon as Backend released one of the eight load slots and finished before the critical final SDK; raising the pool limit alone is not supported by this sample.

Three local-only commands passed exact full artifact-output comparison: an explicit primer, one warm profiled listing, and one listing after a unique main.go comment edit. The source, lock/config and original engine binary were restored; the retained engine was stopped. No Cloud command ran. A short SDK focused-test process may have overlapped the primer or warm profile before the parent stopped it. These are attribution samples, not ordinary wall-time benchmarks, candidate improvements, or estimates of stable latency.

The profile also separates the remaining dynamic work. The first configured Address.container consumed331.49ms warm /288.61ms after edit. The Go.modules call then consumed365.66/292.65ms, including Gomod.modules287.79/261.85ms. The three nested test collections ran concurrently; repeated Address.container reconstruction added roughly30–36ms before those calls. These inclusive intervals overlap and must not be summed as independent CPU cost.

Four registration processes remain in static loading, and two actual backend function processes remain in expansion. `phase-ownership-numeric.json` labels the workspace load job that owns each process and Git advertisement. An owning job does not necessarily identify the process's module: for example, a frontend load can launch its SDK's registration process, and greetings includes a dependency registration. There is no inferred identity from timing or `/runtime` alone.

The largest safe next decision is whether to defer the execution-only configured base while preserving typed Container semantics. A module-load pipeline is a separate larger design: current loading holds a batch mutex; the base's workspace-bound Address resolution would need sibling module availability and can re-enter that loader. Entry-point arbitration, source deduplication, global alias/path conflicts, repairing-mode failures and authority must remain deterministic. See `pipeline-review.md`. The167–193ms window is an optimistic opportunity bound before accounting for these constraints, and upstream static metadata can change it.

Source-only scaling findings remain unmeasured: independent root validity checks are currently sequential, owned file names use interpreter insertion sort, and Dang List.uniq performs quadratic comparison. Sorting cannot simply be deleted: filesystem walk order for `a/x.go` versus `a.go` differs from byte-order sorting. No new implementation is included in this diagnostic.
