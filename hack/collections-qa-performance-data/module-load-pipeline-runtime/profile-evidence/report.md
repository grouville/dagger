The scheduling prototype starts the last of nine top-level source resolutions earlier, but the saved profiles show a much smaller change in the critical catalog interval. Each arm was profiled once, immediately after the exact full check-list primer, in baseline→candidate order. These profiles are for attribution; use the ordinary ABBA results for performance decisions.

| Saved diagnostic | Baseline | Candidate |
| --- | ---: | ---: |
| Last top-level source start, relative to profile origin | 185.73 ms | 38.74 ms |
| Catalog (`Workspace.artifacts`) | 655.53 ms | 631.74 ms |
| Collection expansion (`Artifacts.__itemsJSON`) | 869.92 ms | 867.62 ms |
| Query interval union | 1556.39 ms | 1530.80 ms |
| Git advertisement interval union | 310.50 ms | 303.40 ms |
| Git advertisements | 7 | 7 |
| Runtime processes | 6 | 6 |

Both captures have zero open operations and zero dropped events. Four runtime processes are temporally enclosed by the catalog, and two by expansion, in each capture. The catalog-process interval unions are 400.00→342.62 ms and overlap the catalog's other work. They cannot be added to network intervals or treated as independent savings.

The dispatch shift is 147 ms, whereas the observed catalog difference is 24 ms and the query-union difference is 26 ms. This confirms that the old whole-job limit delayed work and that the new source/asModule stages overlap, without establishing that the delayed source was the final critical branch. Temporal ordinals are not matched module identities; no guessed module name is emitted. There is no permit/enqueue marker or complete source→asModule identity reconstruction in these captures.

The same seven fresh Git admissions and six processes remain. The change reorganizes existing work rather than removing that work. It increases the possible top-level resource envelope from eight whole jobs to separately bounded eight-source/eight-asModule stages. Neither this two-profile attribution nor the small warm matrix establishes fresh-volume or large-workspace peak-memory behavior.

Safe evidence consists of `numeric.json`, this report and the numeric reducer source. Raw wcprof files remain private. The reducer emits only fixed operation labels, counts, hashes, anonymous temporal ordinals and durations.
