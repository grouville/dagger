# Collections discovery: decode each Dang schema once per session

September 24, 2026. On the existing experimental stack, ten warm measurements
per variant give **2.987 s → 2.827 s** combined medians for
`dagger check -l --all` in greetings-api: about 160 ms / 5.4% in this run.
Both alternating blocks favor the change. The 500 ms target remains unmet.

## Change and cache boundaries

Every Dang evaluation used to open and decode its schema JSON file. In this
listing, 21 evaluations consume only six distinct schema files. DagQL already
caches the files; it does not automatically cache the consumer's JSON decoding.

The engine now shares decoded introspection data through `GetOrInitArbitrary`,
keyed by session ID and the schema File's engine-unique result ID. The caller
already holds that File. Different files, views or hidden-field contents cannot
be substituted just because two modules have the same name. Session release
reclaims the entry, and failed decoding does not poison subsequent attempts.
No global map, TTL, filesystem cache or distributed-cache assumption is added.

Dang adds self types, sorts fields and attaches parent links during evaluation.
Each caller therefore receives a deep copy of the freshly decoded JSON tree.
Immutable strings can be shared; mutable slices and pointers cannot. Inferred
types, evaluators, GraphQL clients and execution results remain outside this
cache. The file reader also closes immediately after decoding, instead of
remaining open throughout the evaluation.

For K calls using U schema files, JSON decoding goes from K passes to U, plus K
structural copies. If B is the JSON byte count and N the number of structural
nodes, work changes from roughly O(K × B) to O(U × B + K × N). This is not a
universal asymptotic improvement when B and N scale together, or U equals K.
The useful differences here are repeated parsing eliminated, immutable text
shared, fewer allocations, and fewer file opens. The cache retains O(U × N)
decoded structure for the session; a schema used only once incurs a copy with
no repeated-decoding benefit.

## Same command, application and baseline

- Application: greetings-api `14d684fccf75a137de96f3f0c7eb8c6dafef2d3e`.
- Go module: `1784ff37eb3dd1aacab7aaff91b1d86e311cc8de`.
- Control: the previous stack, including the public-Git-ref reuse commit
  `4f8f48d39a`. The candidate adds this schema change.
- Both retain the experimental Dang syntax cache, split TypeScript imports and
  prebuilt TypeScript SDK runtime. These are not ordinary source-branch build
  timings. The schema change itself does not require those prototypes.
- Same CLI, full 14-row listing, configured Go base and Playwright service.
  Every sample starts a fresh CLI/session against a warmed engine; CLI exit is
  included. No Cloud cache. Broken `SSH_AUTH_SOCK` omitted symmetrically.

Builds/tests run outside the timing windows. Both variants are warmed, then
their execution order alternates. Profiling is separate from reported timings.
The candidate's first population of a new engine volume took 29.794 s and is
retained as a warmup. It is not a paired cold-cache comparison; no new cold
speedup is claimed.

## Warm results

| Five runs per variant | Control median (range) | Candidate median (range) |
| --- | ---: | ---: |
| First block | 2.869 s (2.831–2.991) | 2.768 s (2.641–2.823) |
| Repeat | 3.064 s (2.983–3.328) | 2.851 s (2.831–2.930) |

All ten corresponding pairs favor the candidate. The two block medians improve
by 3.5% and 6.9%; the combined-median difference is 5.4%. This is a small local
sample, not a promise for other machines or modules.

Each block starts after ten seconds below 2% full I/O pressure and 5% CPU
some-pressure. During measured commands, sampled CPU some-pressure is 7.95% /
8.22%, and full I/O pressure is 0.21% / 0.08%. Work itself can create pressure;
these figures do not attribute delays to individual processes. The measurements
are much less affected by contention than the previous Git investigation.
Sample-window bounds use result-file timestamps minus CLI elapsed durations,
with 250 ms sampling resolution. Raw readings are retained.

## wcprof and isolated cost

| Operation | Control | Candidate |
| --- | ---: | ---: |
| JSON decodes | 21 | 6 |
| Cumulative decode duration | 281.7 ms | 92.4 ms |
| Independent schema copies | 0 | 21 |
| Cumulative copy duration | — | 13.4 ms |
| Decode plus copy | 281.7 ms | 105.8 ms |

These durations overlap other operations; the 175.9 ms reduction is not an
additive prediction of CLI wall-time savings. Both profiles contain zero
dropped events and zero open operations. Profiled CLI times, excluded from
the medians above, are 2.769 s and 2.711 s.

Three repetitions of a synthetic 500-type microbenchmark give approximately
11.5 ms / 3.28 MB allocated for JSON decoding, versus 0.83 ms / 0.91 MB for
copying: about 14× faster and 72% fewer allocated bytes on a cache hit. This
microbenchmark excludes the initial decode, File access and cache lookup.
It is not a 14× speedup of discovery.

## Correctness and upstream scope

All 20 measured warm listings match the expected output byte for byte. All
12 edit validations pass, including comment changes, test renames/additions,
module addition and restoration. They independently check expected keys and
compare complete output between engines; individual edit timings are retained
without a per-edit speedup claim.

Sixteen actual CLI runtime calls across both engines pass using existing
repository fixtures: own/secondary-type self-calls, dependency enums, local and
dependency interfaces, and a Dang module entrypoint. The entire
`core/sdk/dang/v2` test package passes under the race detector. New tests cover
deep mutation isolation, concurrent shared decoding, different file/session
keys, error retry and released-session rejection. This does not replace the
complete integration suite or benchmark execution of the application's checks.

Code commit: `5f7989b041`. The engine change is independent of the static SDK entrypoint work. It is
reviewable separately and enabled in a normal build; only the benchmark's
surrounding stack uses the existing prototypes. The typed copy routine must
track changes to Dang's introspection model. Moving it beside that model, or
generating it with the model, is a useful upstream follow-up. Retaining mutable
inference state across callers would require a different correctness argument
and is deliberately outside this implementation.

The [evidence directory](collections-qa-performance-data/schema-decode/)
contains timings, exact output, edit/runtime checks, profiles summarized by
operation, host samples, scripts and binary/profile hashes. The next substantial
cost remains the two overlapping TypeScript description processes, roughly one
second each. Dang source/type processing also remains measurable; parsing JSON
less often does not remove those evaluations.

Both benchmark engines are stopped with their volumes retained. Both exceeded
Docker's ten-second shutdown grace period (exit 137, no OOM flag); shutdown is
not recorded as graceful and is outside all CLI timings.
