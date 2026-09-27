The direct JSON projection removes one unnecessary CLI request. It is still an isolated prototype: this small trial does not establish a speedup across all listing commands.

The same engine and the same optional `baseAddress` Go module served both CLIs. Both CLIs were rebuilt with identical effective historical d685 source, dependencies and VCS stamp; only the two projection source files differ. All 38 local calls passed. Ordered check, artifact and generator listings matched; the native workspace, actual generation and standard check smoke passed without skipped checks. Copied and original fixtures were restored, the temporary engine was removed, the original engine/init stayed untouched and stopped, and its volume was preserved. There were no Cloud calls.

| Ordinary flow | Baseline median | Projection median | Candidate − baseline, each paired observation |
| --- | ---: | ---: | --- |
| `check -l --all`, n3/arm | 1,153.9 ms | 1,134.7 ms | −80.9, −13.0, −7.9 ms |
| `list -a`, n3/arm | 1,106.2 ms | 1,182.8 ms | +113.0, +11.2, −427.4 ms |
| `generate -l`, n3/arm | 777.0 ms | 754.4 ms | −68.4, −22.6, −4.9 ms |
| New main.go comment then check listing, n2/arm | 1,199.3 ms | 1,167.2 ms | +15.4, −79.7 ms |

All raw values and per-command CPU/I/O/pressure counters are in `runtime-numeric.json`. Samples alternated CLI order; these are small correlated observations, not a stable distribution. The first baseline greetings primer cost 20.624 s on the newly copied source path. All primers, native correctness smoke and profiles are excluded from these medians. This is not a cold comparison. The native generator writes an ordinary project file; it is not SDK generation.

The separately primed check profiles provide the mechanism evidence. Main-client requests fall from six to five; total nested query phases fall from 234 to 233. `Artifacts.id` falls from three to two and `Query.node` from 58 to 57. The removed request also removes 15 scoped-implementation hits and one each of the five per-query preparation phases. Every `call_exec` class has the same execution count in both profiles. Both have four module-runtime processes, seven Git admission probes, nine module trees and two core trees. No open or dropped operations were recorded.

Catalog and expansion now run serially inside one query. Their observed handoff shrinks from 24.26 to 2.81 ms. Expansion itself remains similar, 343.47 versus 341.53 ms. Catalog takes 591.08 versus 575.30 ms; that independent variation must not be attributed entirely to the projection. The whole profiled calls take 1,140.96 versus 1,091.04 ms. Inclusive operation durations overlap and cannot be added as savings.

Artifact listing is unresolved. Two pairs favor baseline and one favors projection. The final pair has elevated host I/O pressure in both arms, but these counters do not establish the cause. This trial profiles checks, not artifact listing. It therefore supports eliminating redundant work and a modest check/generator signal, not a broad performance or no-regression claim. A separate bounded artifact-only confirmation is prepared; no extra run is included here.

The API seam is `Artifacts.XXX_ItemsJSON`, not an exported raw selector. It preserves client affinity, receiver immutability, omitted versus explicitly empty dimensions, ordinary object-ID argument prerequisites, errors and cancellation. Composing the query can change the raw GraphQL error path to include ancestors. The existing global-alias fake server was adapted only to wrap the JSON leaf at its actual response path; its Go/TypeScript/Dang assertions remain. Three other ID-then-projection readers are intentionally unchanged for attribution: dimensions, artifact type descriptions and load failures.
