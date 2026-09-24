# Collections discovery: the Go SDK import and layer reuse

Measured September 24, 2026, following the [cold-start investigation](collections-cold-performance.md).
The target remains faster cold and warm `dagger check -l --all` on the complete
`greetings-api` configuration. Neither experiment below is enabled in normal
builds. The retained engine change adds finer wcprof boundaries.

## Where the import time goes

The SDK's compressed blobs already ship inside the engine image. This operation
does not download them from `registry.dagger.io`.

A complete, correct 14-row listing took 29.876 s. Its Go SDK root filesystem
import took 4.552 s, broken down as follows across nine layers:

| Work | Wall time within this import |
| --- | ---: |
| Prepare snapshots | 0.004 s |
| Apply layers: decompress, hash and extract files | 4.378 s |
| Commit snapshots | 0.152 s |

The compiler layer alone took 2.537 s to apply. The prefilled Go build-cache
layer took 1.020 s. Copying the compressed SDK content took another 0.501 s
before the import; reading image metadata took 0.0006 s. Per-layer lock waits
are also recorded. Durations use `end_ns - start_ns`, not the end timestamp.

An isolated `_builtinContainer` query reading `/usr/local/go/VERSION` avoids
application builds and registry pulls. It took 5.356 s, including a 3.907 s
filesystem import. Its separate ten-second CPU capture contains 7.25 CPU-seconds:
1.94 s in syscall execution and 1.85 s in the SHA-256 block function. Of the
hashing call stacks, approximately 0.48 s belongs to content copying and 1.38 s
to layer application. These are CPU samples, not additive wall-time savings.

The first full-listing CPU capture failed at HTTP readiness; its wcprof and
complete output remain valid. The isolated CPU capture waits for HTTP readiness
and succeeds. No conclusion here relies on the missing CPU profile.

## Experiment 1: omit compiler test files from the SDK payload

The compiler archive contains 16,705 entries. Removing `usr/local/go/test`,
`testdata` subtrees within `usr/local/go`, and `*_test.go` files there leaves
6,762 entries. This removes 39.39 MiB of file contents; the compressed layer
changes from 60.85 to 49.89 MiB. Compiler binaries, production sources, licenses,
documentation and prefilled compilation caches remain present.

The experiment rewrites that OCI layer and updates its diff ID, config and
manifest. Other layers remain byte-identical. It uses ordinary Dagger content
identity and invalidation; it does not cache listing answers. Simply deleting
these files in a later image layer would still require extracting the original
files first, so that would not implement this experiment.

Both sides use the same experimental Dang syntax cache, split TypeScript bundle
and prebuilt TypeScript SDK runtime. App `14d684f`, remote Go module `1784ff3` and
all application settings are unchanged. Each cold sample uses a new, empty
Dagger cache volume and an already-ready engine. Host page cache, image storage
and upstream services are not reset. Runs are serial and profiled from the first
command. These are not measurements of an ordinary build without the prototypes.

| Pair and execution order | Original SDK | Trimmed SDK |
| --- | ---: | ---: |
| Full listing, original then trimmed | 27.272 s | 26.011 s |
| Go SDK import in that pair | 4.445 s | 3.245 s |
| Full listing, trimmed then original on new volumes | 45.134 s | 42.442 s |
| Go SDK import in that pair | 4.799 s | 3.995 s |

All four listings match the complete 14-row reference, with no dropped wcprof
events. The two listing pairs save 1.261 s and 2.692 s, respectively. The large
variation between pairs prevents a stable latency or percentage claim.

Five alternating warm runs give 3.092 s original versus 3.001 s trimmed.
This does not establish a substantial warm improvement. All twelve edit cases
pass independent key checks and full-output comparisons: unchanged, comment,
rename, added test, added module and restoration. The trimmed rename sample
takes 4.106 s versus 3.010 s original; no edit-latency improvement is claimed.

### Why this is not adopted

The application uses `golang:1.26-alpine` for its backend and checks. The original
SDK shares the compiler layers with that image. Trimming the SDK changes their
content identity and loses that reuse.

After the warm and edit checks, each engine was asked for the VERSION file from
the application's previously unmaterialized Go base image:

| First use of the unchanged application Go image | Original SDK | Trimmed SDK |
| --- | ---: | ---: |
| Command wall time | 3.573 s | 6.235 s |
| Layers applied | 0 | 3 |

Both return the same file. In the trimmed case, the full compiler layer takes
2.750 s to apply; two tiny suffix layers also need applying because their parent
chain changed. The original case reuses all five layers without applying any.

This additional 2.662 s can erase the listing gain in a normal development loop.
These are two commands measured at different stages, not a newly timed combined
listing-and-check workflow. The direct evidence is the lost layer reuse. Keep
the original shared layers as the default. No full application check was timed
in this experiment, and no engine-builder change is enabled.

## Experiment 2: overlap hashing with extraction

A containerd v2.2.5 overlay uses a bounded 32 KiB `io.Pipe` producer to hash and
feed large layers while the consumer extracts files. It preserves original
layer bytes and identities and still consumes the full stream for the digest.

The isolated VERSION query succeeds, but command time changes from 5.356 s to
5.568 s and filesystem import from 3.907 s to 4.254 s. This one comparison does
not demonstrate a gain. The prototype is not adopted; it has not received full
error, cancellation, race or end-to-end validation. Do not mistake passing the
existing applier package's path-parsing test for validation of this pipeline.

## Retained work and current baseline

`image.importLayer`, `image.prepareSnapshot`, `image.applyLayer` and
`image.commitSnapshot` now separate extraction from snapshot bookkeeping in
wcprof. Existing snapshot reuse, concurrent-prefix, failed-import, mounted-failure
and canceled-waiter tests pass. The four full cold profiles contain no dropped
events and all benchmark listings are checked against expected output.

The last broader five-run warm comparison remains 6.435 s on the original
collections branch, 4.852 s with the integrated engine/CLI changes and 3.053 s
with the Dang and TypeScript prototypes. The latest experimental-stack control
is 3.092 s warm and 27.272 / 45.134 s cold. We have not reached 500 ms and have
not measured this stack with the in-flight distributed-cache changes.

The [variance and distributed-cache follow-up](collections-cold-cache-analysis.md)
compares those two cold profiles, correlates the slowdown with host disk pressure,
and adds three controlled repetitions: 28.631 / 26.091 / 32.984 s. A new five-run
warm median is 3.107 s. These repeat the same executable; they are not another
code speedup.

Scripts, exact outputs, timings, profile summaries and hashes are in
[the evidence directory](collections-qa-performance-data/go-import/). Large
profiles and binaries remain outside Git; their hashes and source locations
are recorded in `provenance.json`. The pipeline patch targets containerd, not
the Dagger source tree. The scripts use the documented local benchmark layout.
