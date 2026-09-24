# Isolated Dang syntax-cache experiment

These historical measurements use `--extra-debug` engines. The
[normal-engine audit](collections-normal-mode-performance.md) repeats the
full comparison without that flag and with Kyle's remote Go module.

Measured September 24, 2026, after the [committed discovery changes](collections-qa-performance.md).
On the same `greetings-api` checkout, adding only the experimental syntax cache
reduces the warm median from **4.522 s to 3.663 s (19%)**. This reproduces the
earlier prototype's improvement. The 500 ms target remains unmet.

## Changes to describe to the team

The committed engine indexes artifact dimension paths and aliases, shares
collection receivers within a request, avoids duplicate module installation,
and reuses prepared schemas within the same caller/session authority. The CLI
loads listing metadata in bulk in one discovery session. Large listings are
buffered so output remains complete.

The Go module collects test names during its existing immutable-snapshot scan,
removing another search pass, transport of match metadata, and a quadratic
file-to-match join. Existing user PRs also improve module-config/environment
reads, lazy schema digests, empty telemetry uploads, and nested-client shutdown.
Together these committed changes measured **6.16 s to 4.40 s** in the earlier
five-round comparison with the original collections branch.

The new experiment adds a **syntax-only cache in Dang**, not yet part of the
production source on this branch. Its new comparison is **4.52 s to 3.66 s**;
do not combine medians from different runs to claim an isolated total speedup.

## Why DagQL does not already avoid this work

DagQL caches the operations expressed through its graph, subject to their
inputs and scope. It does not automatically memoize arbitrary Go code inside a
runtime invocation. Reusing a source snapshot does not reuse the parsed syntax
tree. A fresh Dang declaration/evaluation can parse unchanged bytes again.

Syntax depends on source content. Evaluation additionally depends on imports,
the schema, and the current client. The prototype hashes the file bytes, looks
up a pristine syntax tree, and gives each consumer a fresh copy. Inference,
evaluation, and normal Dagger result caching keep their existing boundaries.

A Go application edit generally leaves the Dang implementation unchanged, so
parsing can be reused while discovery still recomputes for the edited Go input.
A Dang source edit changes the key. This is whole-file reuse, not incremental
parsing. A hit costs O(source bytes + syntax-tree size); the normal parser's
algorithm is unchanged on a miss. The gain is avoiding repeated parser work and
allocations, rather than making a cache hit constant time.

## Matched measurements

Both variants use the committed CLI, the same local Go module at `c84f15b119`,
and the same disposable `greetings-api` checkout at `14d684fccf`.
The exact command is `dagger check -l --all`, from the application directory,
including CLI shutdown. The harness only selects the binary and engine.
All 14 checks and the full SDK/lint/Playwright configuration are retained.

The experimental engine uses the same Dagger source with two parser call sites
redirected through a build overlay, and Dang v2.1.4 with three changed files:
`eval.go`, `parse_cache.go`, and its tests. The unrelated Dang map-merge change
is explicitly excluded. Both engines have dedicated cache volumes. The broken
SSH agent is omitted on both sides. Profiling and correctness suites run
separately from latency measurements.

| Warm sample | Committed | With syntax cache |
| --- | ---: | ---: |
| 1 | 4.522 s | 3.752 s |
| 2 | 5.022 s | 3.936 s |
| 3 | 4.741 s | 3.562 s |
| 4 | 4.451 s | 3.663 s |
| 5 | 4.515 s | 3.657 s |
| Median | **4.522 s** | **3.663 s** |

Variants alternate order between warm rounds. Every complete output is byte
identical. Two fresh-nonce edit sequences, without warming the edited input,
give the following individual samples:

| Edit | Committed, samples 1 / 2 | Syntax cache, samples 1 / 2 |
| --- | ---: | ---: |
| Comment | 5.148 / 5.149 s | 3.995 / 4.036 s |
| Rename test | 4.921 / 4.934 s | 3.940 / 3.986 s |
| Add test | 5.009 / 5.064 s | 4.149 / 4.109 s |
| Add module | 5.217 / 5.126 s | 4.419 / 3.919 s |
| Restore | 4.537 / 5.130 s | 3.577 / 3.822 s |

Expected sets, ordering, and descriptions match in every case, including the
15-row added-test and 16-row added-module cases. Sources are restored afterward.

One empty-engine-cache pair gives **48.175 s / 48.862 s**. This does not show a
cold improvement. The engine is already ready when timing starts; host and
upstream caches are retained. This is a single pair, not a cold distribution.

## Attribution

Separate wcprof captures contain **20,900 operations each**, zero dropped
events, and zero open operations. Invocation counts are unchanged:

| Internal stage | Calls on each side | Median duration before / after |
| --- | ---: | ---: |
| Dang runSource | 19 | 109.47 / 7.37 ms |
| Dang selfTypes | 10 | 105.69 / 4.42 ms |
| Dang objectDirectives | 10 | 147.49 / 4.20 ms |

These are stage durations, not additive whole-command savings. Concurrent
stages overlap. The two TypeScript processes still take about 1.92 s each in
the cache-enabled profile, and overlap one another.

Three microbenchmark repetitions compare ordinary parsing against a warm
content lookup plus clone, including file reads. For the 19.8 KB `go.dang`,
median time is **83.63 ms / 5.30 ms**, with roughly **24.42 MB / 1.73 MB**
allocated per operation. For `gomod/main.dang`, it is **70.86 ms / 4.38 ms**.
Those parser improvements do not imply a sixteen-fold faster whole command.

## Size and upstream status

The prototype adds 196 implementation lines and 118 test/benchmark lines,
changes one library call site, and redirects two engine call sites. It keeps
at most 16 entries, admits sources up to 128 KiB, and coalesces simultaneous
parses of identical content. This is process-local and disappears on restart.

The difficult part is ownership: Dang inference mutates AST nodes. The current
copy uses checked reflection and must never expose the cached template to an
evaluator. An upstream version should provide a maintained typed clone or
immutable syntax with separate evaluation state, review memory limits and
diagnostics, and run full CI. The existing source limit is not a precise byte
budget for retained AST memory. No public UX or DagQL API change is required.

The Dang package tests and cache race tests pass, covering independent copies,
same-size/same-timestamp edits, diagnostic source locations, invalid syntax,
concurrent inference, and capacity. Selected Dagger integration groups also
pass: directives, attachables, workspace arguments, versioned syntax, self
calls, lazy forcing, load-error reporting, collection listing, selection,
dimensions, and batch replacement. These are focused checks, not full CI.

Raw timings, patch files, microbenchmarks, profile summaries, and validation
commands are in [the evidence directory](collections-qa-performance-data/syntax-cache/).
