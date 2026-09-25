# Collections discovery: reuse the public Git advertisement

September 24, 2026. This change removes a redundant Git metadata request from
warm discovery. It uses the existing session cache, and is independent of SDK
entrypoint work. The complete listing still takes seconds; this is not a
500 ms result.

## What changes

When resolving an HTTP Git dependency, the engine checks whether the repository
is public before considering implicit credentials. That check already downloads
the advertised refs. Previously it discarded them, and a subsequent metadata
load could run `git ls-remote` against the same repository again.

The visibility probe now retains its advertisement and primes the existing
remote metadata cache for the same session and anonymous repository inputs.
The later lookup reads that entry. Protocol selection, ref resolution and the
CLI UX stay the same.

- No sharing across sessions, TTL or filesystem side cache. A new command
  rechecks visibility and gets fresh metadata.
- Explicit credentials, URL userinfo, SSH and service bindings bypass priming.
- The first metadata initializer wins, including an already-running load.
  Values are serialized before publication; callers receive separate decoded
  copies, so changing a caller's HEAD cannot change another caller's refs.
- Actual symbolic HEAD, annotated tags and peeled refs are preserved. The
  conversion uses the raw advertisement because go-git's `AllReferences` can
  infer a symbolic HEAD that the server did not advertise.

For a repository requiring both operations, metadata discovery goes from two
remote advertisements to one. Network work remains O(R) in the number of refs;
this removes a duplicate transfer/process, rather than changing that order.
Conversion sorts the refs in O(R log R) to preserve Git's deterministic ordering.
The probe retains O(R) metadata for the session, in addition to the canonical
cache payload. Session release reclaims both. Large-ref repositories are worth
profiling before considering an immutable serialized representation shared by
the two entries.

## Measurement boundaries

The command remains `dagger check -l --all` in greetings-api `14d684f`, with Go
module `1784ff3`, all 14 checks, the configured Go base and Playwright service.
Both engines use the previous experimental Dang syntax cache, split TypeScript
imports and prebuilt TypeScript SDK runtime. These are not ordinary branch-build
timings, and are not directly comparable to Kyle's cold 29.88 s.

The control is the preceding stack; the candidate adds only this Git change and
its profiling boundaries. The CLI is identical. Each sample is a fresh CLI
process/session against an already-running engine with a warm cache, including
CLI exit. `SSH_AUTH_SOCK` is omitted on both sides. No Cloud cache is involved.
Commands alternate in order; builds/tests do not overlap timed commands.

## Warm results

Five measured runs per variant in each block, with every output checked byte for
byte against the same expected listing:

| Block | Control median (range) | Candidate median (range) |
| --- | ---: | ---: |
| Initial | 3.470 s (2.889–6.243) | 3.254 s (3.117–3.434) |
| Repeat | 4.659 s (4.069–8.335) | 4.018 s (3.843–19.346) |
| Low-I/O start criterion | 4.383 s (3.218–7.418) | 4.451 s (3.431–5.952) |

These blocks do not support a reliable full-command speedup percentage. The
second block encountered substantial host contention: a spot check during it
showed 47.2% full I/O pressure averaged over ten seconds. The candidate's
13.33 s sample began with a one-minute load average of 9.23 on eight logical
CPUs. These are observations, not an attribution of delay to a particular
process. The slow samples remain in the evidence.

The final block started only after ten seconds below 2% full I/O pressure.
Its continuous 250 ms samples show just 0.17% full I/O pressure across the
block, but 49.0% CPU some-pressure: tasks were frequently waiting for CPU.
That block establishes no complete-command gain either. The Git request
reduction is demonstrated; the size of its end-to-end benefit remains uncertain
on this shared host.

## Profiling and correctness

Separate wcprof runs show five `GitRepository.ref` executions totaling
298.9 ms before and 2.3 ms after. The candidate records seven public
advertisements and zero separate `git.lsRemote` operations. The control predates
those two finer instrumentation points, so its absence of those events must
not be interpreted as zero requests. Both profiles have zero dropped events
and zero open operations. Parallel/nested durations are not additive wall-time
savings. Profiled command times are 3.834 s and 2.842 s, not the unprofiled
benchmark medians.

All twelve edit checks pass: unchanged, comment-only edit, test rename, test
addition, module addition and source restoration, on both engines. They check
expected keys independently and compare complete output between engines.
Individual edit timings are retained; there is no stable edit-latency claim
from a single sample per case. Application checks themselves were not executed
by this experiment.

Focused tests pass with and without the race detector. A real local Git HTTP
advertisement matches the Git CLI, including symbolic HEAD and annotated tags.
Sixteen concurrent clients share one HTTP request; cached metadata survives
caller mutation without sharing it. New sessions observe changed refs/private
visibility. Credential, service, SSH and URL-userinfo cases do not prime the
anonymous metadata cache. External-provider authentication integration tests
were not rerun.

## Remaining work and evidence

The candidate profile still contains two overlapping TypeScript processes of
about 1.03 s each, 21 Dang schema decodes totaling 285 ms, plus module loading,
configured container evaluation and CLI overhead. The schema-decode total is
not 285 ms guaranteed off the critical path. Static SDK definitions belong to
the existing SDK entrypoint work; this change does not duplicate that effort.

The [evidence directory](collections-qa-performance-data/public-git-refs/)
contains raw timings/output, edit validation, profiling summaries, test logs,
repeat scripts and provenance. Large binary/profile files remain in the lab
with their hashes recorded. The code commit is `4f8f48d39a`. The new engine code can be reviewed independently
of the experimental SDK stack used to measure it. It is enabled because it
removes a demonstrated duplicate transfer while preserving the session/cache
boundaries, not because these timings prove a stable whole-command percentage.

The candidate engine created for this experiment is stopped; its volume is
retained. Shutdown exceeded Docker's ten-second grace period (exit 137, no
OOM flag), so it is not recorded as graceful. Engine shutdown is outside all
CLI timings above.
