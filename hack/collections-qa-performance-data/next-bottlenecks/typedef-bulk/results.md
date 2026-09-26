# Rejected for this workload: bulk object function namespacing

The generic immutable function builder has better scaling, but its first engine
consumer did **not** improve the normal greetings-api listing. Keep the experiment
and evidence; do not ship the namespacing change on these results.

## Real CLI result

Eight alternating warm pairs, exact `dagger check -l --all`, same static-TS +
combined-Dang experimental baseline, normal direct telemetry, unchanged configured
service base, same SDK payload and image, distinct warmed engine volumes:

| Variant | Median | Range | Samples |
| --- | ---: | ---: | ---: |
| Frozen control | 2.131 s | 2.061–2.319 s | 8 |
| One bulk namespacing consumer | 2.284 s | 2.033–2.550 s | 8 |

The candidate is 7.2% slower by median in this series. This does not establish a
universal regression, but it establishes no reason to ship it as a performance
win. Every command's 14 listed rows matched byte for byte. Existing TypeScript
`source entries` and `build entries` calls matched the baseline before timing.
The engine, CLI and module worktree are not a claim about upstream tip performance.

Ordinary wcprof captures recorded zero dropped events. Their engine operation
spans were 1.409 s control and 1.430 s candidate. Publication calls decreased
2,074→1,997. `ObjectTypeDef.__withFunction` calls decreased 474→219, with 46
`__withFunctions` calls replacing part of them. Inclusive summed publication
wall time was 258→145 ms, and single-function builder time 80.6→16.9 ms plus
5.2 ms in bulk calls. These sums overlap and include cache paths; they are not
serial critical-path savings. The candidate's separate profiled CLI wall was
4.636 s despite a 1.430 s engine span; that outlier is not charged to the bulk
resolver. The ordinary unprofiled eight pairs above are the wall-time comparison.

## What the workload actually builds

A separate diagnostic engine records member counts only, never source or argument
payloads. It observed **17 executed object replacement groups**, all with the
same number of functions before and after. All functions in each object were
replaced. Total replacements: 104. Group-size distribution:

| Functions per object | Executed groups |
| ---: | ---: |
| 1 | 1 |
| 2 | 5 |
| 3 | 1 |
| 4 | 3 |
| 5 | 2 |
| 6 | 1 |
| 8 | 1 |
| 12 | 1 |
| 14 | 1 |
| 18 | 1 |

The largest real group is 18, versus up to 1,000 in the synthetic builder test.
The microbenchmark builds from empty; this consumer replaces existing members.
Small collections, temporary index allocation and unchanged surrounding schema,
SDK, publication, and telemetry work limit the case for this consumer. No single
mechanism is proven to explain the full +7.2% median difference. A fallback for
small groups could be tested later, but should not be added on speculation.

## Algorithm and semantics

Existing `WithFunction` clones the immutable object slices and scans matching
members for every call. Repeated distinct appends produce quadratic copies/scans.
The prototype clones once and uses temporary indexed names while preserving the
original earliest-match semantics: nonempty `OriginalName` OR normalized `Name`.
Collisions can create multiple matching positions; simple name→position maps
would be incorrect. The prototype keeps generation-checked candidate positions,
using heaps only when names actually collide. Unique construction is expected
linear; adversarial rename sequences can require O(n log n). No index survives
publication and no cache identity, authority, module isolation or TTL changes.
A singleton delegates to the original method.

The only real consumer is the object-function loop in `Module.namespaceTypeDef`.
Each function is transformed in its previous order; changed IDs are gathered,
then a private `__withFunctions` resolver loads them through the current server
and publishes the final object once. Fields, constructors, interfaces, core type
builders, and other loops are unchanged. Intermediate publication/error timing
is intentionally different; transformation order and final metadata are tested.

## Tests and synthetic evidence

Focused core/schema tests passed, including randomized equivalence against the
sequential implementation (250 deterministic streams), duplicate/alias/empty
original names, nils, object and interface variants, receiver immutability,
metadata/default preservation, and collection schema/namespace regressions.
A real private GraphQL resolver test retains the final object in a second cache
session, releases its producer session, and then loads the function and argument
IDs successfully. This exercises dependency ownership rather than only slices.
Broad all-SDK integrations were deliberately not run after rejecting the candidate.

The original helper microbenchmark (three repetitions per case, 100 ms each)
measured sequential→bulk medians:

| Distinct appended functions | Time | Bytes allocated |
| ---: | ---: | ---: |
| 1 | 0.322→0.469 µs | 800→800 |
| 10 | 8.301→4.356 µs | 16,160→5,376 |
| 100 | 495.03→44.13 µs | 721,632→51,696 |
| 1,000 | 42.007→0.463 ms | 52,843,525→565,712 |

These measurements predate the singleton delegation optimization in the actual
engine candidate; their exact helper is preserved separately. They establish a
scaling opportunity for genuinely large builders, not a greetings-api CLI gain.

## Reproduction and provenance

- Driver: `benchmark.py`; raw `benchmark.log`, `measurements/results.json` and
  `measurements/summary.json` include every value/output/IO-pressure sample.
- Profiles: `measurements/{profile-control,profile-bulk,diagnostic-bulk}.wcprof`;
  numeric summaries in `measurements/profile-summary.json`. In this format `d`
  is the operation end offset, so durations are `d - s`.
- Engine hashes/image/SDK manifest: `engine-manifest.json`.
- Final source hashes: `source-manifest.json`; patch:
  `engine-consumer-final.patch`; ordinary/diagnostic overlays are preserved.
- `artifact_batch.go` is frozen to `c12a34663b` in both overlays. Later shared
  batch changes are excluded. Frozen baseline engine SHA begins `a1b41acd`;
  bulk candidate SHA begins `094f77de`.
- Focused test output: `consumer-unit.log`; original helper benchmark:
  `bench.log`, `bench-summary.json`, `typedef_bulk_bench_original.go.txt`.
- abba2 was left unchanged; task-owned abba1 was stopped after profiling.
