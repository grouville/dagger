# Collections discovery performance

For the current, full-application comparison using Kyle's exact
`greetings-api` command, see [the team report](collections-qa-performance.md).
The measurements below also include earlier synthetic workloads and prototypes.

Experiment against [Artifact Collections, dagger/dagger#14221](https://github.com/dagger/dagger/pull/14221),
pinned at `175dca038268639231c21323cd7aaa1d746617dd`, on branch
`perf/collections-discovery`. The Go module comparison is against
`dagger/go@9af8ac5` (`collections`). Measurements were made on September 23,
2026, on an Intel i5-9300H Linux host with a dedicated local development engine.

The latest end-to-end results use the combined experimental stack described
below: discovery changes, four existing PRs, and the isolated Dang syntax-cache
prototype. The syntax prototype is not wired into this checkout's dependencies.
Building this checkout alone does not reproduce the combined stack's timings.

## Which user command is being measured?

The original 1,024-row Go workload is `dagger check -l --all
--generated=false go/modules/tests/run`. It expands every test check. It is
**not** the default `dagger check -l` workflow, which keeps dimensions collapsed.

The collections branch exposes these distinct discovery surfaces:

| Command | What it shows in the Go fixture |
| --- | --- |
| `dagger list` | Available artifact types and collection commands; no runtime keys |
| `dagger check -l` | Three check paths, including generation staleness checks; no expanded keys |
| `dagger list go-modules` | Eight module keys |
| `dagger list go-tests` | 1,024 test keys with their module keys |
| `dagger list checks go/modules/tests/run` | 1,024 check artifact links |
| `dagger list -a` | All discovered artifact links |

A discovery listing does not execute the leaf checks. `dagger api call` also
exposes collection `keys`, `get`, `subset`, `list`, and `batch`; those API calls
are separate from browsing artifacts and running checks.

## Changes

* Preserve shared schema prefixes through immutable selection filters, then
  memoize expansion within one request and workspace identity. Shared collection
  receivers enumerate once; independent receivers still overlap. Ordering,
  cancellation, failure propagation, and deferred leaves remain intact.
* Index ancestor paths and dimension prefixes for dimension-key discovery.
  Index display-name aliases in each exact schema-path scope.
* Return CLI row metadata through private `Artifacts.__itemsJSON`. Public
  per-artifact APIs still work. This avoids publishing engine objects for every
  URI, description, and dimension key that the CLI immediately flattens again.
* Discover `dagger list` commands through private `__typeDefinitions`. The PR's
  existing `types` endpoint expands runtime collections; using it before user
  filters made unrelated receivers run, and broke five listing-format tests.
  Runtime `types` behavior remains available through the public API.
* In the separate Go module checkout, produce `.testnames` during the existing
  source scan. Reuse parsed directives across modules' include graphs. Remove
  per-directory glob queries, the second ripgrep scan, per-match GraphQL fields,
  and the file-by-match join. Read selection and names in one library call.

## Measured results

The 512-row fixture has eight outer keys, four inner keys, and sixteen check
paths sharing those receivers. Five unprofiled warm repetitions measured:

| Measurement | PR baseline | Optimized |
| --- | ---: | ---: |
| Expanded listing median | 3.83 s | 1.39 s |
| Four concurrent clients, median | 6.80 s | 1.55 s |
| Four concurrent clients, throughput | 0.55 commands/s | 2.53 commands/s |
| Recorded engine operations per profiled listing | 27,716 | 2,156 |

The eight-client run completed eight commands in 2.34 s (3.42 commands/s), with
no failures. Sixteen clients completed sixteen commands in 4.17 s (3.84
commands/s), with 4.03 s median and 4.16 s maximum latency. Throughput is
flattening while per-command latency rises: this is useful evidence of local
saturation, without a service returning a rate-limit error.
Outputs matched byte for byte across all these runs. The bulk
listing field itself took about 37 ms per profiled warm invocation. Core-only
changes with the old CLI still took 3.32 s: removing metadata publication work
was necessary to improve actual command latency.

The real Go fixture has eight modules, sixteen test files per module, and eight
test names per file: 1,024 listed checks. On the same optimized engine and CLI,
five unprofiled warm runs measured **7.53 s → 5.88 s**. Outputs were identical.
Separate three-run wcprof captures recorded **36,824 → 22,227 operations** and
**262 → 78 queries** per invocation. There are no remaining per-directory glob
queries or per-match search results in test-name discovery.

The scanner's shared-dependency benchmark, which creates a fresh index for
every iteration, measured **144.35 ms → 15.13 ms** for 100 modules sharing a
dependency with 100 source files. Parsing is reused within that snapshot;
transitive include output still has to be produced for each requesting module.

Core benchmarks exclude SDK and CLI startup. Both binaries were built before
three alternating runs with `-cpu=4 -benchtime=300ms`; these are medians:

| Work | PR baseline | Optimized |
| --- | ---: | ---: |
| Expand 1,000 paths, one key per dimension | 10.88 ms | 2.86 ms |
| Expand 100 paths × 16 modules × 8 tests | 16.13 ms | 3.96 ms |
| Ancestor pruning, 5,000 artifacts | 542.02 ms | 3.92 ms |
| Resolve aliases, 1,000 dimensions at one path | 575.47 ms | 5.09 ms |

The shared-receiver fixture enumerates 17 receivers instead of 1,700. Small
alias scopes use a bounded scan (at most eight dimensions), avoiding three hash
maps per path in the common one- or two-dimension case.

## Cold starts and invalidation

The first paired empty-engine-volume runs were **50.33 s baseline / 82.51 s
optimized**, with identical outputs. This does not demonstrate a cold-start
improvement. Images, SDK setup, and tool compilation are included; the host OS
page cache and upstream registry caches were not cleared. Both fixtures already
had lockfiles. A separate wcprof run on new volumes investigates those costs.

Restarting each engine with its disk cache retained took **24.73 s / 21.01 s**
for the first command, excluding Docker's restart command itself. These are
single observations. A subsequent Docker restart failed with “did not receive
an exit event”; it is excluded, and no restart median is claimed.

Each edit below was followed immediately by a fresh CLI process, without a
warmup of the edited inputs. The engines stayed running. This comparison uses
the original PR engine/CLI/module versus the discovery engine/CLI/indexed module:

| Edit | Baseline | Discovery changes |
| --- | ---: | ---: |
| Comment only, identical discovery keys | 9.65 s | 6.27 s |
| Rename a test | 9.14 s | 6.09 s |
| Add a test | 9.86 s | 6.33 s |
| Add a module | 10.51 s | 7.13 s |
| Remove additions and restore source | 9.06 s | 5.96 s |

These are individual edits, not latency distributions. Every phase checks the
complete ordered key list, including absence of removed names. Comment-only
edits and the restored workspace also match the original output byte for byte.

`hack/bench-artifact-discovery-invalidation.py` reproduces these edits on a
disposable fixture and restores its files on exit. Its optional `--wcprof-url`
drains the recorder through debug HTTP before each edit's command; it does not
run a discovery query that would warm the new inputs. For empty-cache profiling,
use the regular runner with `--warmups 0 --cold-profile --wcprof-url ...` against
a newly created engine volume.

## Complexity

Let N be schema artifacts, P maximum path depth, D maximum dimension depth,
H module-tree depth, R distinct runtime receivers, and E expanded output rows.
The following bounds assume a fixed number of selector filters; applying many
filters adds their own membership costs.

| Work | Previous structure | New structure |
| --- | --- | --- |
| Ancestor pruning | All artifact pairs, repeatedly collecting dimension chains | Path trie plus dimension-prefix tries; O(N(H + PD)) |
| Exact-path aliases | Filter and clone the selection per template, then scan aliases repeatedly | Group by exact path, hash identifiers/aliases once, O(N(H + D)) construction and constant-time alias lookup |
| Collection enumeration | Repeated traversal for every leaf sharing a receiver | Request-local expansion DAG; R receiver enumerations |
| Go file/test join | Every file filters all K search matches: O(FK) | Names indexed while reading source bytes, then ordered/deduplicated locally |
| Shared dependency parsing | Reparse shared source bytes for each reaching module | Parse once per snapshot; retain successful results and errors |

Producing E distinct rows still costs at least O(E). Constructing their keys
costs O(EH) here. This change does not claim sublinear full enumeration, or
linear transitive include output in a densely connected module graph.

The static indexes contain schema metadata. The dynamic expansion memo belongs
to a single request and includes workspace identity. There is no process-wide
cache of mutable collection keys. A new scanner process indexes a new immutable
workspace snapshot, so source changes invalidate the generated name files.

A further scanner prototype caches parsed go.mod files and resolved local
replacement edges per snapshot. In a separate alternating benchmark it changed
the already-optimized 100-module scan from **15.63 ms to 14.33 ms**. Its cycle,
replacement-edit, Go-version-edit, and error-repair checks pass. It remains a
separate prototype: saving 1.3 ms here does not address the remaining seconds.

The Dang library's module-root membership filter is also quadratic. Replacing
its list scan with `reduce` plus immutable `Map.with` is not a linear solution:
Dang v2.1.4 copies the map and insertion-order keys on each `with`. A bulk index
constructor could build once in O(M) while preserving order and immutability.
The current eight-module fixture does not establish that this is a significant
wall-time bottleneck; broad persistent-map work needs its own workload evidence.

## The 500 ms target

The target is **500 ms for a fresh CLI command after each edit**, with the same
complete, ordered listing and correct invalidation. It has not been reached.
The following experiments use the optimized Go module and an isolated worktree
containing the discovery changes plus four existing PRs by `grouville`:

| Existing PR | Cost addressed |
| --- | --- |
| [#14180](https://github.com/dagger/dagger/pull/14180) | Dang nested HTTP transport cleanup; intermittent shutdown tail |
| [#14182](https://github.com/dagger/dagger/pull/14182) | Empty Cloud metric upload during shutdown |
| [#14183](https://github.com/dagger/dagger/pull/14183) | Eager schema digest computation |
| [#14179](https://github.com/dagger/dagger/pull/14179) | Directory uploads merely to read module config or probe `.env` |

Their combined focused tests passed. Five alternating warm observations had
medians of **7.38 s discovery-only / 6.19 s with these PRs**; variable tails mean
this does not isolate the contribution of any one PR. None removes the
synchronous CLI telemetry Git enrichment discussed below.

A 30-second engine CPU profile then attributed **65.1% of sampled CPU** to Dang
parsing. Added wcprof stages showed three full source parses per invocation:
self-type metadata, source evaluation, and object-directive metadata. Their
per-call medians were about 162, 207, and 187 ms respectively in that capture.
These are overlapping CPU/wall observations, not additive command latency.
Dang telemetry flush had a **1.5 ms median** in the same capture.

Ordinary native calls already have the module's own types in their schema, and
only registration consumes the retained object directives. Skipping the two
metadata passes for ordinary calls reduced the profiled warm command median
from **5.78 s (three runs) to 4.52 s (five runs)**, with identical output.
Registration and entrypoint declaration behavior remain intact. The focused
Dang and collections integration groups passed, including self-calls,
interfaces, source errors, directives, list formats, and batch replacement.

With that change, separately profiled immediate edits took:

| Edit | Seconds |
| --- | ---: |
| Comment only | 4.44 |
| Go version in module config | 4.58 |
| Rename a test | 4.74 |
| Add a test | 4.40 |
| Add a module | 4.54 |
| Remove additions and restore source | 4.53 |

All complete ordered key lists passed validation. These are individual edits,
not p95 estimates. They show that a roughly ninefold reduction is still needed.

Parser memoization is not a useful shortcut on these sources. Three isolated
samples with Dang's `Memoize(true)` changed median `go.dang` parsing from
82.0 to 122.2 ms and allocation from 23.9 to 115.1 MB; `gomod/main.dang` changed
61.4 to 96.4 ms and 19.3 to 90.6 MB. The runtime does not enable that option.

An isolated experiment caches only pristine parsed syntax, bounded by entry count
and source size, keyed by source content. Each invocation must receive a fresh
copy before inference, including fresh import nodes: inferred ASTs retain
per-call GraphQL clients and cannot safely be shared. Workspace keys and
evaluated values remain uncached by this experiment. It reduced the profiled
warm median to **2.59 s** (five runs, identical output). Source evaluation's
median became **12.4 ms**. Immediate edits measured 2.61 s for comments, 2.78 s
for Go config, 2.63 s for renaming/adding tests, 2.77 s for adding a module,
and 2.90 s for restoring the workspace. All ordered keys passed validation.
The Dang library suite, race checks on concurrent evaluation, content edits
preserving file size/mtime, capacity, source-location rewriting, and the focused
engine integration groups passed. The prototype uses checked reflection to
clone pristine syntax; it is **not an upstream-ready AST API** and is not wired
into this checkout's dependencies. A typed clone or immutable syntax plus
per-evaluation state belongs in Dang itself.
Editing the Go module's Dang implementation to remove one test name from every
module changed the listing from 1,024 to 1,016 keys; restoring the source restored
the original listing byte for byte. This checks module-code invalidation as
well as the project-input edits above. The conservative metadata shortcut keeps
the original passes for runtime schemas without `IncludeSelfInDeps`.
Final engine checks also passed `@cache(Never)` repeated forcing and explicit
ID pinning, workspace arguments, old/new syntax versions, self-calls, and the
SDK client attachable isolation tests (including denial of parent secrets and
host files).

The native-Git telemetry experiment retains labels and the existing reader as
a fallback. On this packed checkout, fresh commit reads measured **237.3 ms
with go-git / 5.9 ms with native Git** (three sample medians). Existing PR-merge
handling tests and new fallback, linked-worktree, environment-override, and
partial-clone tests passed. Three alternating whole-command pairs were noisy:
2.98 s versus 3.05 s median, so **no end-to-end latency improvement is claimed**.
This remains a separate candidate, not a change to workspace source resolution.

The remaining wcprof capture includes 78 queries and 23 Dang invocations per
listing. Across five listings, schema building accounts for 7.20 s of self-time
and 15 `Query.git` executions for 2.95 s of self-time. Those operations overlap;
the numbers are not a sum of removable command latency. Git's HTTP visibility
probe is cached per session and participates in selecting credentials. Removing
its session scope merely to make a benchmark faster would change semantics.
Likewise, `ModuleSource.asModule` has a per-client input and attached module
results carry ownership: a process-global cache of loaded client schemas is not
a safe substitute. Reusing immutable declarations while binding fresh clients
is the next substantial architectural boundary, alongside CLI shutdown.

Use `bench-artifact-discovery-invalidation.py --budget-ms 500 ...` to make the
target an explicit end-to-end acceptance check. It collects every edit, restores
the fixture, writes `budget.json`, and exits unsuccessfully if any phase misses.
The first unprofiled gate run failed all seven phases at **4.70–6.41 s**.
An unrelated lint engine was using roughly six logical CPUs during that run;
those observations are retained as contended latency, not substituted for the
earlier profile comparison or silently excluded from the acceptance result.
The 500 ms requirement remains unmet.

### Further profiling and normal CLI listing

A 20-second CPU capture after the syntax prototype recorded 25.39 CPU-seconds:
30.6% in GC marking, 12.8% in `ModuleObject.Install`, and 10.2% in JSON decoding.
These overlap call stacks and are not additive wall-time savings. Default
lookup repeatedly copied parent client metadata through JSON even when no
`.env` defaults existed. A small shortcut now leaves workspace constructor
settings first and skips parent lookup only when the source defaults and
expansion context are both empty. Its initial unprofiled samples alone did not
show a clear whole-command gain: medians 2.626 versus 2.634 seconds.

Nested client initialization also appended modules whose attached dependency
schema already included themselves. Avoiding that duplicate installation plus
the empty-defaults shortcut reduced a five-listing wcprof capture from 111,380
to 91,275 operations. Schema-build self-time changed from 7.20 to 0.737 seconds
across the capture, while the whole-command profiled median was still 2.471
seconds. Counts establish removed work; these separate captures are not a
controlled attribution of wall-time savings to either shortcut alone.

Normal typed/collection `list` previously started a silent engine session to
register dynamic CLI commands, closed it, then started another session to list
items. It now resolves the selector inside the listing session. Help and
completion still discover dynamic commands before rendering. Nothing is retained
across commands, and all selectors, source resolution, and authorization continue
through the engine. Three alternating unprofiled pairs, same engine and identical
output, measured:

| Listing | Two sessions, median | One session, median |
| --- | ---: | ---: |
| Module keys | 2.834 s | 1.857 s |
| Test keys | 3.385 s | 2.551 s |
| Check artifact links | 2.519 s | 2.388 s |

Two-command wcprof captures also reduced `Query.git` executions from 12 to 6,
`ModuleSource.asModule` from 16 to 8, and total operations from 49,608 to
38,794, with no dropped/open events. `list -a -f link` separately listed
2,129 artifact links in 2.961 seconds (one unprofiled unchanged run).

Both CLIs in this comparison use the original Git label reader; the native-Git
experiment is excluded. The engine includes the four existing PRs and the
isolated syntax-cache prototype described above. This is not a claim that the
main checkout alone produces these timings.

The new `--surface` option runs the edit loop against each actual UX path.
Every edited input now contains a unique per-run comment so repeating the
benchmark cannot reuse a previous identical input snapshot. The revert phase
intentionally restores the original content. Collection and artifact listings
sort links; the validator checks their lexical order, while expanded check
listing preserves traversal order. The initial collection run caught a wrong
ordering assumption in the benchmark; it was corrected before the validated
runs below.

| Immediate edit | Default checks | Module keys | Test keys | Check artifact links |
| --- | ---: | ---: | ---: | ---: |
| Comment only | 2.498 s | 2.112 s | 2.964 s | 2.495 s |
| Go version/config | 2.232 s | 1.950 s | 3.987 s | 2.506 s |
| Rename test | 1.430 s | 2.183 s | 2.863 s | 2.683 s |
| Add test | 1.486 s | 2.148 s | 2.586 s | 2.704 s |
| Add module | 1.483 s | 2.088 s | 3.078 s | 2.776 s |
| Revert | 1.411 s | 2.553 s | 2.487 s | 2.439 s |

These are single unprofiled, fresh-process observations on a running engine,
including startup, synchronization, output and shutdown. Unchanged first samples
were 3.553, 1.897, 2.931 and 2.285 seconds respectively; variability is retained
rather than hidden. All output and invalidation assertions passed, and **all
four surfaces failed the 500 ms budget**.

Focused integrations passed self-calls, SDK attachable isolation, syntax
versions, workspace and `.env` defaults, collection CLI formats, aliases,
dimension selection, schema-only listings and batch replacement. Unit checks
also verify ordinary `list` preparation needs no engine connection.

### Reusing prepared schemas within a session

A further change forks an already prepared dependency schema when a nested
client uses the exact same builder and non-module caller. The fork owns its
root and field tables. Module changes and ownership clones rebuild normally;
entrypoint proxy schemas also retain their original construction path. Reuse
requires the same opaque session authority, session ID and parent client ID,
so reusing ID strings after session teardown cannot reuse the preparation.
The identity token retains no client lease. Function execution and cache policy
are unchanged.

Five profiled `list go-tests -f link` runs recorded **13,523 operations per
listing**, down from 19,397 in the preceding two-run capture. There were 19
prepared forks per listing. Total schema-build self-time across the five runs
was 33.7 ms, with another 39.9 ms in forks. The whole-command median was still
**2.324 s**. This is a small, separate capture, not a controlled claim of a
particular latency reduction. Outputs were identical.

Fresh unique edits followed by `list go-tests -f cli` took **2.761 s** for a
comment, **2.568 s** for Go config, **2.609 s** for a rename, **2.651 s** for an
added test, and **2.609 s** for an added module. Ordered output checks passed;
every phase failed the 500 ms gate. The unchanged and revert samples were
3.221 and 2.437 seconds. These observations preceded the additional opaque
session-authority guard, whose focused race checks passed.

The real engine integrations passed collection formats and batch replacement,
workspace settings, syntax versions, self-calls, SDK attachable isolation,
and `@cache(Never)` versus explicit ID pinning. Unit race checks cover concurrent
forks, caller/session separation, reused IDs in a new session, released/unbound
scopes, ownership clones, added modules and isolated field tables.

### Default collection tables and output integrity

Running the exact default command, `dagger list go-tests`, exposed missing
stdout rows: each of three 1,024-item listings produced a different truncated
table despite exit status zero. `tabwriter` makes several writes per row, and
span stdio emits one telemetry record per write into a bounded asynchronous
queue. These timings are rejected as successful listing measurements. The
engine wcprof captures themselves remain complete; that says nothing about
stdout log delivery.

The CLI now buffers listing writes in 32 KiB chunks. A real integration test
checks every byte of 4,096-entry table, link and CLI listings. All formats pass,
as do the existing format tests. The invalidation runner also checks the first
listing against the fixture generator's expected keys, rather than treating
whatever discovery returns first as a correct baseline.

With this fix and the session-authority guard, fresh unique edits followed by
**`dagger list go-tests`**, with no format flag, measured:

| Immediate edit | Complete command |
| --- | ---: |
| Comment only | 2.497 s |
| Go config | 2.475 s |
| Rename test | 2.244 s |
| Add test | 2.588 s |
| Add module | 2.528 s |
| Revert | 2.201 s |

All complete ordered key lists passed, including 1,025 keys after additions and
1,024 after revert. Comment/config/revert output matched the unchanged listing
byte for byte. The unchanged first sample was 2.771 seconds. The corresponding default
`dagger list go-modules` commands took 1.996, 1.870, 2.008, 1.878, 1.859 and
1.840 seconds; module addition changed eight keys to nine and revert restored
eight. Its unchanged first sample was 2.313 seconds. These are single
unprofiled observations on a running engine, with fresh CLI processes and no
priming after edits. Every phase still misses 500 ms.

A separate CLI CPU/trace capture of this command attributed 120 ms of sampled
CPU to telemetry Git labels, including 110 ms reading the packed object index.
The full process had 540 ms of sampled CPU; this is CPU attribution, not a
promise of 120 ms less wall time. Output in that capture contained all 1,024
rows and matched the unprofiled baseline. The same trace records 351 ms
of blocking in telemetry shutdown, versus 8 ms in engine client close. This is
a measured export wait, not a fixed sleep or proof that all 351 ms can be removed.

### Dang immutable-map merge

A separate Dang patch replaces `Map.merge`'s repeated immutable `with` calls
with one privately built result. The cost changes from O(NM + M²) copying to
expected O(N + M) work and storage for maps of N and M entries. Existing keys
keep their positions; right-hand values win; neither input is mutated.

Three isolated benchmark samples per case, four CPUs, give these medians:

| Entries per input, half overlap | Repeated copying | Bulk merge | Allocated bytes, before → after |
| --- | ---: | ---: | ---: |
| 100 | 504 µs | 9.5 µs | 880 KB → 13 KB |
| 1,000 | 56.5 ms | 123 µs | 101 MB → 197 KB |
| 5,000 | 1.77 s | 0.72 ms | 2.27 GB → 820 KB |

The allocation totals are cumulative, not peak resident memory. Large old
cases ran only one iteration per sample because each exceeded the requested
100 ms benchmark duration. The existing Dang map language tests and focused
ordering, overwrite and input-isolation tests passed. This is a standalone
library improvement: it does not change repeated `with` construction, and the
current Go discovery module does not use `merge`, so no listing speedup is
attributed to it. The quadratic module-root membership test still needs a bulk
index API or a different join; replacing it with repeated `with` would retain
quadratic construction.

### Cache-boundary audit

| Layer | Reused work | Invalidation / ownership |
| --- | --- | --- |
| Artifact schema | Prefix/alias indexes | Built from the selected schema; no persisted runtime keys |
| CLI listing | One session for selector resolution and rows | Session ends with the command; help/completion keep dynamic registration |
| One discovery request | Shared receiver expansion | Node plus workspace identity; discarded after the request; calls still use DagQL |
| Go scanner | Parsed source and test-name index | Fresh process over an immutable Dagger directory; container exec identity includes source, helper, mode, and image |
| Nested schemas | Prepared schema fork for the same attached builder | Same session authority and parent caller; fresh root/field tables; mutations and ownership clones rebuild |
| Native Dang metadata | Avoided redundant registration passes | Full registration retained; ordinary invocation still evaluates its function |
| Experimental syntax cache | Pristine syntax templates | Content hash, 16-entry limit, source-size limit, isolated copy before inference; no workspace values or clients retained |
| Git visibility / module ownership | Existing engine behavior | Session/client scopes preserved |

No host-path result cache, mtime-only invalidation, persistent collection-key
cache, cache-volume discovery database, or bypass of function cache policy is
introduced. The syntax prototype only reuses deterministic parsing; it never
skips function execution. The module scanner's generated files remain ordinary
Dagger build outputs and are invalidated through their input graph.

Fresh empty-volume wcprof observations, measured separately in reversed order,
were **39.70 s original / 36.29 s discovery / 33.95 s with the four PRs**.
The scanner helper's cold `go build` took about **17.2 s**; executing its scan
took about **73–83 ms**. A 500 ms first-ever run cannot include that compilation
on this machine. Prebuilt helpers and available images/toolchains are a
separate prerequisite from making the steady development loop fast.

The final prototype was also run once on a newly created empty engine volume
using default `list go-tests` output: **32.79 seconds**, including setup, with
all 1,024 rows matching the warm baseline byte for byte. Its wcprof capture has
16,282 operations, no open operations and no dropped events. The scanner's
`go build` took **17.72 seconds**; lazy base-image materialization recorded
7.93 seconds. These nested/overlapping measurements are not additive. This
remains an engine-cache cold start, not a cleared host page cache or upstream
registry cache. The one-shot engine was stopped after saving the profile.

### Reducing the scanner's cold build

The helper still compiled a legacy gateway mode even though the module only
uses `--all` over a mounted snapshot. That pulled in the Dagger SDK and its
gRPC, protobuf, HTTP and telemetry dependencies. The module now builds with
`-tags=snapshot`; shared parsing/scanning code remains the same, while the
legacy CLI and its tests remain available in the default build. The module's
helper check tests both variants. The enclosing Dagger exec still records the
scanner's timing and stderr; local scanning needs no SDK connection.

Three alternating cold-build pairs on the same pinned Go 1.26.8 Alpine image,
with separate empty compiler and module caches for every sample, measured:

| Measurement | Existing helper | Snapshot helper |
| --- | ---: | ---: |
| Median build | 17.217 s | 4.476 s |
| Binary size | 23,878,341 bytes | 3,928,245 bytes |
| Compile dependency packages | 457 | 80 |
| Downloaded dependency modules | 40 | 1 |

The compiler image was already available; these timings exclude pulling it.
Builds enabled `-x` logging in both variants. The snapshot build only downloads
`golang.org/x/mod`. The executable remains an ordinary Dagger build output,
keyed by source, build flags and toolchain; mutable caches only accelerate Go's
own dependency and compiler work.

Both variants' unit suites passed. Their bare, test, generate and combined scan
modes produced byte-identical output over the module repository (137, 171,
182 and 216 files respectively). The real module discovery, source-policy,
generation-directory and helper checks also passed.

This is principally a cold-build gain. A separate seven-surface, three-pair
warm comparison preserved every output byte but did not show a broad latency
improvement. Module-key medians were 1.687 versus 1.724 seconds, test keys 2.232
versus 2.239, and expanded checks 2.283 versus 2.297. Artifact-check table samples
were noisy and slower in the snapshot group (2.848 versus 3.632 seconds); that
result is retained, not counted as an improvement.

The actual cold collection command was then repeated on another newly created
empty engine volume, with the same engine and CLI as the 32.79-second capture:
**16.53 seconds**, with identical complete output. wcprof records 16,282
operations, no open or dropped events, **4.56 seconds for the helper build**
and 4.81 seconds for lazy image materialization. Image/network timing differs
between these single observations; only the alternating isolated builds above
establish the repeatable compilation gain. Host page caches and upstream image
caches were not cleared. The new engine was stopped after saving its profile.

### Reusing CLI listing metadata

One command now holds the immutable Artifacts ID and dimension definitions for
each distinct include-path scope. Selector resolution and row loading use the
same selection. Runtime keys are still resolved by the engine; nothing is
retained across CLI commands. Existing collection selection, list-format,
schema-list and complete 4,096-row output integration checks pass.

A three-command wcprof comparison recorded **five Workspace.artifacts
executions per listing → one**, and **13,520 → 12,071 operations per listing**.
Both CLIs use the original telemetry Git reader and the same scanner source.
The seven-command wall-time comparison was mixed: module keys improved from
1.944 to 1.655 seconds, while test keys and all-artifact listings were slower.
Five more alternating pairs measured 2.209 → 2.019 seconds for test keys and
2.130 → 2.203 seconds for all artifacts. This establishes removed work, **not
a consistent end-to-end latency win**; the change remains a local candidate.

### Bulk module paths and query placement

The Go tool previously requested library module objects, fetched each object's
path, then constructed its own module objects merely to obtain their paths.
`Gomod.modulePaths` now exposes the same ordered and filtered paths in one call.
The existing `modules` API builds its objects from those paths. Go's ordinary
collection listing uses the paths directly; requests that exclude skipped
tests or generation still evaluate those settings on the module objects.
Workspace `findRoots`, source-based module eligibility, and include/exclude
rules are preserved.

The first 1,000-module wcprof capture fell from **47,341 to 23,424 operations**
and **3,017 to 1,017 queries**, with the same complete output. It also exposed
the next repeated query: the module asked for `Workspace.cwd` inside the path
conversion loop. The final implementation reads cwd once for that result and
passes the string into a private pure path conversion helper. The public
workspace-path API remains unchanged. This reuses a value within one call,
not across source snapshots or sessions.

The module-root membership predicate also uses Dang's native `contains`
instead of an interpreted `any` callback. Three isolated interpreter samples,
including every successful lookup in a 1,000-root list, measured **1.226 s →
7.97 ms** and **1.35 GB → 4.98 MB** cumulative allocation. This is a large
constant-factor improvement; membership remains **O(RM)** for R candidates
and M accepted roots. It is not claimed as a linear-time index.

A binary-search prototype was rejected. Despite logarithmic comparisons,
passing the list into the helper caused Dang's value materialization to copy
and inspect every element on every call. Its 1,000-root median was 295 ms,
slower than native membership and still carrying quadratic list-copying work.
The probe also verified the subtle ordering rule: scanner roots follow lexical
**go.mod file** order, not root-directory order. Neither the binary-search
helper nor an immutable-map construction loop is included in the module change.

The library discovery check validates bulk paths against object paths, cwd,
ordering, includes and excludes. The six focused Go checks also passed module
discovery, discovery from subdirectories, collection and test execution,
introspection/skip settings, and invalid/empty-module handling.

After moving cwd out of the loop, the 1,000-module capture records **15,432
operations and 18 queries**, with no open/dropped events. The first bulk-only
comparison and the final comparison each used three alternating unprofiled
pairs with identical CLI/engine binaries and byte-identical output:

| Module count | Before bulk paths | Bulk paths | Final comparison baseline | Bulk paths + one cwd read |
| --- | ---: | ---: | ---: | ---: |
| 100 | 2.718 s | 1.710 s | 2.835 s | 1.637 s |
| 1,000 | 10.607 s | 3.251 s | 14.617 s | 2.397 s |

The changed baseline between rounds is retained. These are local medians of
small samples, not a universal sixfold speedup or a p95 estimate. For the final
1,000-module pairs, the one-minute host load average before samples was
1.21–1.80 on eight logical CPUs. The membership test is still quadratic; the
query count for this module-key workload is now independent of module count,
and output production still requires linear work.

A final cold run with the complete module/CLI changes on another new empty
engine volume took **17.99 seconds**. All 1,024 rows matched the warm result;
wcprof recorded 14,695 operations, 55 queries, no open/dropped events, a
4.79-second helper build and 6.12 seconds of lazy image materialization. The
earlier thin-helper-only cold run was 16.53 seconds; these individual network
and image observations are retained separately, not treated as a distribution.
The final one-shot engine was stopped after saving the evidence.

Three alternating groups of four concurrent `list go-tests` clients also
preserved every output byte. Across twelve commands per variant, median
latency changed from **4.042 to 3.286 seconds**; median group throughput changed
from **0.857 to 1.013 commands/second**. This is bounded local contention, not
an external rate-limit test. No HTTP 429 is claimed.

### Final command and edit matrix

These three alternating pairs compare the thin scanner before bulk paths
against the final module, on the same prepared-schema/syntax-prototype engine
and the same CLI candidate. Both sides retain the original Git label reader.
All command outputs match byte for byte. These measurements include fresh CLI
startup, engine work, complete default-format output, and shutdown.

| Command | Before bulk paths | Final module |
| --- | ---: | ---: |
| `dagger list` | 1.526 s | 1.408 s |
| `dagger check -l` | 1.504 s | 1.397 s |
| `dagger list go-modules` | 1.713 s | 1.515 s |
| `dagger list go-tests` | 2.090 s | 1.979 s |
| `dagger list checks go/modules/tests/run` | 2.255 s | 2.250 s |
| `dagger list -a` | 2.350 s | 2.046 s |
| Expanded test checks | 2.559 s | 2.328 s |

The preceding bulk-only round measured 1.402 seconds on both sides for overview
and 1.431 versus 1.427 for default checks. Those schema-only commands do not
use the changed runtime module enumeration, so their final 100 ms differences
are not attributed to the module optimization. Artifact-check samples also
remain variable; no broad multiplicative warm speedup is claimed.

Every edit below uses unique source content and is followed immediately by a
fresh command, without warming the edited inputs. The engine stays running.

| Immediate edit | Default checks | Module keys | Test keys | Check artifacts | Expanded checks |
| --- | ---: | ---: | ---: | ---: | ---: |
| Comment only | 1.417 s | 1.828 s | 2.138 s | 2.776 s | 2.541 s |
| Go config | 1.413 s | 2.361 s | 2.134 s | 2.158 s | 2.533 s |
| Rename test | 1.427 s | 1.664 s | 2.106 s | 2.229 s | 2.564 s |
| Add test | 1.397 s | 1.812 s | 2.082 s | 2.098 s | 3.055 s |
| Add module | 1.374 s | 1.787 s | 2.279 s | 2.288 s | 2.596 s |
| Revert | 1.425 s | 1.468 s | 1.981 s | 2.013 s | 2.706 s |

All 35 phase/output assertions passed, including added and removed keys, and
all 35 phases failed the **500 ms** budget. These edit observations are single
samples, not distributions. In surface order, unchanged first samples were
1.819 s, 1.648 s, 2.856 s, 2.351 s, 2.435 s.
The fixture was restored after each surface.

`hack/bench-artifact-discovery-matrix.py` makes the seven-command comparison
reproducible. It alternates variants, preserves raw output and load readings,
rejects any output mismatch, and optionally enforces `--budget-ms 500` after
collecting the complete matrix. Its destination must be new to avoid replacing
previous evidence. Profiling, cold starts and edit loops remain separate runs.

### Running from the project directory

The comparisons above invoked the CLI from the Dagger checkout and passed
`--workspace`. The CLI's telemetry Git labels use its working directory, so
that includes metadata from the larger Dagger Git repository. A separate copy
of the fixture was given a local initial commit, then every command was run
from that project directory **without `--workspace`**, using the final code.
No telemetry setting was disabled. This is the literal edit-then-command loop;
its small Git history does not represent the label cost of a large packed repo.

| Immediate edit | Default checks | Module keys | Test keys | Check artifacts | Expanded checks |
| --- | ---: | ---: | ---: | ---: | ---: |
| Comment only | 3.412 s | 1.626 s | 2.127 s | 2.175 s | 3.448 s |
| Go config | 1.261 s | 1.630 s | 2.484 s | 2.072 s | 2.435 s |
| Rename test | 1.392 s | 1.676 s | 2.055 s | 2.007 s | 4.707 s |
| Add test | 1.304 s | 1.630 s | 3.108 s | 2.161 s | 2.521 s |
| Add module | 1.292 s | 1.630 s | 2.104 s | 2.043 s | 2.544 s |
| Revert | 1.294 s | 1.494 s | 1.791 s | 1.798 s | 2.208 s |

All output/invalidation checks passed, the fixture returned to a clean Git
status, and all 35 phases still failed the 500 ms gate. Unchanged first samples
in surface order were 2.172 s, 1.570 s, 1.863 s, 1.938 s, 2.231 s.
The slower individual samples are retained; moving cwd is not presented as a
controlled latency improvement. `--from-workspace` on the invalidation runner
reproduces this invocation mode, and each phase records the actual cwd.

## Reproduction

Use an isolated dev engine and CLI built from the same checkout. For containers
used by integration tests, build the CLI with `CGO_ENABLED=0`; Alpine fixtures
cannot execute a CLI linked against the host's glibc. See the repository's
engine-debugging instructions for the engine build workflow.

```sh
# An explicit Git boundary is essential for these temporary fixtures.
python3 hack/bench-artifact-discovery-fixture.py /tmp/discovery-project

python3 hack/bench-artifact-discovery.py --runs 10 --jobs 1 \
  --output /tmp/discovery-latency -- \
  ./bin/dagger --engine container://dagger-engine.collections-perf \
  --workspace /tmp/discovery-project check -l --all --generated=false

# Separate profiling from unprofiled latency measurements.
python3 hack/bench-artifact-discovery.py --runs 3 --jobs 1 \
  --output /tmp/discovery-profile --wcprof-url http://127.0.0.1:6061 -- \
  ./bin/dagger --engine container://dagger-engine.collections-perf \
  --workspace /tmp/discovery-project check -l --all --generated=false

# Compare all seven Go discovery commands, alternating before/after processes.
# Both workspaces must expose the same generated Go fixture and module names.
python3 hack/bench-artifact-discovery-matrix.py --runs 3 \
  --baseline-cli /path/to/baseline/dagger \
  --candidate-cli /path/to/candidate/dagger \
  --baseline-engine container://dagger-engine.before \
  --candidate-engine container://dagger-engine.after \
  --baseline-workspace /tmp/go-before --candidate-workspace /tmp/go-after \
  --output /tmp/go-discovery-matrix

# Generate a real Go workspace using a local checkout of dagger/go.
python3 hack/bench-artifact-discovery-fixture.py /tmp/go-discovery-project \
  --go-module /path/to/dagger-go
# Normal collection UX: edit, then immediately list with default table output.
python3 hack/bench-artifact-discovery-invalidation.py \
  --workspace /tmp/go-discovery-project --cli ./bin/dagger \
  --engine container://dagger-engine.collections-perf \
  --surface collection-tests --format table --budget-ms 500 \
  --output /tmp/collection-edits

go test ./core -run '^$' -bench '^BenchmarkArtifactDiscovery' \
  -benchmem -benchtime=300ms -cpu=4 -count=3
```

Build `wcprof-analyze` from the `dagger.io/wcprof` module and run it against
`runs.wcprof`. The runner enables the engine's native `--profile` recorder,
drains setup events, and saves raw stdout/stderr, output hashes, timings, and
`results.json`. Increase `--jobs` to 4 or 8 for bounded contention tests.
New samples also record host load before and after each command and CPU count;
inspect those when latency changes without an implementation change.

For comparisons, compile both benchmark binaries first and alternate their
runs. Keep builds, test execution, and load tests out of latency measurements.
Keep cold module/toolchain setup separate from warm runs. The first properly
rooted Go setup took 35.9 s; that is not a cold-cache comparison between versions.

## Limits and remaining work

**This is not yet instant end-to-end discovery.** The full Go command still
takes seconds despite cheap cached source scanning and reuse of prepared nested
schemas. Remaining work includes repeated Dang schema decoding/evaluation,
module registration, session-scoped Git resolution, and CLI initialization and
shutdown. These need critical-path measurements; their aggregate overlapping
self-times cannot be subtracted from command latency. A global cache of
previously returned keys would make this faster at the expense of correct
discovery after changes.

CLI-side costs also matter: one CPU profile attributed about 220 ms of CPU to
Git metadata loading in this checkout, and the accompanying synchronization
profile recorded about 420 ms waiting in telemetry shutdown. These overlap
other work and are follow-up candidates, not guaranteed additive savings.

Telemetry Git metadata is not a prerequisite for discovery. `LoadDefaultLabels`
currently loads it synchronously before analytics initialization, even when
analytics tracking is disabled. It supplies commit/branch/author labels and
remote/ref context used to identify local module calls in traces. Workspace Git
operations used to locate or resolve source are a separate requirement. A
future change should defer or make telemetry enrichment cheaper while retaining
source links; deleting all Git reads is not equivalent. Telemetry shutdown is
another measured boundary, not evidence of a fixed 420 ms sleep.

No external rate limit was observed or claimed. Repeating a warm command can
hit engine caches without contacting a registry or GitHub. The concurrency
experiments measure local contention and throughput; they cannot guarantee an
external HTTP 429. A specific service's quota needs a separate experiment with
request counters and its actual quota contract.

There were no dropped events or open operations in the reported wcprof dumps.
Parallel self-times overlap and must not be added as command latency. Combined
dumps contain separate CLI/query roots and inter-run gaps: the analyzer's final
blocking chain and counterfactual ranking do not describe the whole CLI's
critical path. Use counts, individual durations, and unprofiled wall time together.

Small samples characterize this machine, not a production p95. Early timing
runs used Python's timeout polling, which can add up to roughly 50 ms to a
sample; the committed runner uses a separate deadline thread and blocking wait
to avoid that quantization.

One aborted fixture inherited `/tmp/.git` and scanned `/tmp`, uploading 3.8 GB.
Giving it its own Git root fixed the experiment. That run is excluded from all
performance comparisons. The fixture generator always creates a Git boundary.

## Validation

Focused core/schema/CLI tests cover naming, key filters, ordering, cancellation,
workspace isolation, shared failures, immutable source trees, serialization,
and persistence relocation. A differential test compares trie pruning against
the original exhaustive definition. Shared expansion passed `-race`.

The real `TestCollections` command-list, schema-list, list-format, selection,
dimension-item, and batch-replacement tests pass against the modified engine.
The Go scanner tests and existing `tests-collection-check` pass, including
batch/single-test execution, skipped modules, build constraints, duplicate names,
and nested modules. Dang v2 formatting and `git diff --check` pass.

### Prebuilt scanner and the cold Go image cost

The final source-build cold profile above recorded 6.12 seconds in
`lazy:Container.from`. The matching engine log shows five compressed layers
with a total size of **71,405,777 bytes**. The Go toolchain layer alone is
67,308,359 bytes. Its layer-apply operation took **2.430 seconds**, and all five
apply operations total **2.655 seconds**. Fetching the layers and snapshot setup
account for the remaining time in the 6.12-second span; the log does not give a
precise network-only duration. A separate `call_exec:Container.from` class
recorded **2.12 seconds of self-time** for image metadata resolution. These are
cold image preparation costs, not Go process startup or source scanning.

The code path agrees with those boundaries: `Container.FromCanonicalRef`
first calls the resolver's `Pull`, then `SnapshotManager.ImportImage`; the
latter applies the image layers in order. Retaining this image for a prebuilt
scanner would still pay its cold pull and unpack cost. A retained engine cache
reuses the content and snapshots; editing application Go source does not
require downloading the image again.

Two isolated module copies tested the already-built **3,928,245-byte static
linux/amd64 scanner**. One installed it into the same pinned Go Alpine image;
the other used an empty container filesystem. Both loaded it through an
ordinary `currentModule.source.file` and `Container.withFile`, mounted the same
content-addressed source snapshot, and ran the same scanner. The binary's
parsing code, source filters, scan flags and discovery UX were unchanged. These
are packaging prototypes; the module patch still builds the scanner from
source and contains no embedded executable.

Three rounds rotated the order of all three variants. **Every sample used a
new, empty engine-cache volume**, the same engine and CLI binaries, and the
same 8-module / 1,024-test fixture. Each timed command was a fresh CLI process
running `list go-tests`, with wcprof enabled and no priming command.

| Scanner packaging | Cold samples | Median |
| --- | --- | ---: |
| Build from source in Go image | 16.870 / 15.312 / 16.085 s | **16.085 s** |
| Prebuilt binary in Go image | 11.595 / 11.520 / 12.503 s | **11.595 s** |
| Prebuilt binary in empty filesystem | 4.660 / 4.807 / 4.867 s | **4.807 s** |

Prebuilding alone saves **4.490 seconds (28%)** by the medians. Prebuilding and
removing the compiler image saves **11.278 seconds (70%)**, or about **3.35x**.
All nine outputs have the same complete baseline SHA-256
`409cdeef9bf48f2df2a46e1cccfddaf2f1650f1838e33b980570d936eaa88e48`.
wcprof records no open or dropped events, no `go build` in either prebuilt
variant, and no `Container.from` image work in the empty-filesystem variant.
The remaining cold time includes SDK module fetching, schema/runtime setup,
source transfer, scanning and CLI lifecycle; **500 ms remains unmet**.

The engine process was ready before each timed command: this measures an empty
engine cache, not engine installation or startup. Host page caches and upstream
registry/CDN caches were retained. The prebuilt executable was already local;
the command includes sending it to the engine, but **does not measure fetching
a published scanner image or release binary**. Production delivery would add
that distribution cost. These timings also do not establish a warm-edit win,
because Dagger already caches an unchanged helper build.

A production version can retain Dagger's caching model: build a scanner
artifact for each supported platform, pin its content/version alongside the
module, and use an ordinary container exec keyed by that artifact, flags and
workspace content. The packaging experiment introduces no persistent workspace
index, host-path memoization or cache-volume shortcut for discovery results.

Evidence is under `/tmp/collections-perf/prebuilt-scanner`: `run-cold.py`,
`cold-summary.json`, all nine command outputs and wcprof captures, filtered
`image-events.json` records, `original-image-events.json`, and `prototype.json`
with the executable digest. `prepare.py` records the exact prototype edits.
All nine temporary engines were stopped after capture; their cache volumes
remain available for inspection.
