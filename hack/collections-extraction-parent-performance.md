# Collections discovery: reusing archive parent paths

September 24, 2026. **This experiment improves an isolated image import slightly,
but does not establish faster complete discovery. It remains disabled.**
The SDK definition work is left to the existing SDK entrypoint implementations
reviewed in the [cold analysis](collections-cold-cache-analysis.md#existing-sdk-work-use-moduleentrypoint).

## The independent optimization

The earlier CPU profile showed repeated filesystem checks during layer
extraction. Containerd resolves the parent path and ensures its directory exists
for each archive entry, including consecutive regular files in the same directory.

The prototype retains one successfully resolved parent between consecutive
regular entries. It excludes resolved aliases, resets on non-regular entries
and whiteouts, and does not enable reuse automatically with custom callbacks.
The standard overlay importer explicitly opts in. Nothing survives the current
extraction call. Layer bytes, digest verification, snapshot identities and
Dagger cache ownership are unchanged.

For a run of `k` sibling files at depth `d`, expensive parent filesystem walks
can fall from roughly `k × d` to one depth walk. String processing, per-file
metadata, file writes and hashing still run. The optimization keeps one cache
entry, not an expanding map. Unordered archives can still require a parent walk
per entry; this does not make all extraction constant time.

This is a patch against containerd v2.2.5, applied in an isolated dependency copy.
The branch's normal dependencies and engine behavior remain unchanged.

## Same application and measurement boundaries

The full command is `dagger check -l --all` in greetings-api `14d684f`, using
Go module `1784ff3`, the configured backend Go base and Playwright service.
Both variants use the existing experimental Dang syntax cache, split TypeScript
imports and prebuilt TypeScript SDK runtime. Both retain the original Go SDK
image. These are not timings for an ordinary branch build without the prototypes.

Cold means an empty Dagger volume on an already-ready engine. Engine provisioning,
image download for that engine, host page-cache reset and shutdown of the engine
after measurement are excluded. CLI shutdown is included. No Cloud cache is used.
Runs are serial, with wcprof and host pressure sampled every 250 ms. No builds
or tests run alongside the timed commands.

## Isolated Go SDK import

An internal builtin-container query reads `/usr/local/go/VERSION`, avoiding
application compilation and external image pulls. Every result matches exactly.

| Execution order | Original rootfs import | Prototype rootfs import |
| --- | ---: | ---: |
| Original, prototype | 3.724 s | 3.480 s |
| Prototype, original | 3.750 s | 3.351 s |

The measured import savings are 0.245–0.399 s, about 7–11%. Complete isolated
command times are 6.037 / 4.723 s in the first pair and 5.042 / 4.429 s in the
second. Other command boundaries vary too; their entire difference cannot be
attributed to this parent-path change.

## Complete cold listing

The first full series kept its first two engines running for later warm tests,
but stopped the next two engines after their samples. That unequal lifecycle
could affect the next sample through background work or pending disk writes.
Its raw results are retained: original 29.121 / 27.152 s, prototype
44.985 / 37.903 s. The two prototype runs coincide with 23.47% / 15.44% host
iowait, versus 0.59% / 0.45% for the originals. This is not proof of which
process caused that pressure, nor grounds to declare those results irrelevant.

The repeat uses the same shutdown step after every cold sample:

| Chronological sample | Complete listing | Go rootfs import | Host iowait | Host full I/O stall |
| --- | ---: | ---: | ---: | ---: |
| Original 0 | 26.006 s | 4.204 s | 0.52% | 0.149 s |
| Prototype 0 | 26.463 s | 4.083 s | 0.47% | 0.138 s |
| Prototype 1 | 26.033 s | 4.097 s | 0.52% | 0.154 s |
| Original 1 | 37.040 s | 4.734 s | 19.84% | 11.068 s |

The corrected lifecycle does not eliminate host pressure. Under low pressure,
the prototype saves about 0.1 s on Go rootfs import while the complete listings
remain around 26 s. The slow final original would inflate an average speedup;
no full-command percentage improvement is claimed. Host PSI measures concurrent
pressure, not latency charged directly to this command.

All eight complete cold listings match the same 14 rows byte for byte. All
twelve cold profiles, including isolated imports, have zero dropped events and
zero open operations.

## Warm listings, edits and correctness

Five alternating unprofiled warm runs per engine give:

| Variant | Median | Range |
| --- | ---: | ---: |
| Original | 3.100 s | 3.000–3.198 s |
| Prototype | 3.129 s | 3.000–3.557 s |

There is no demonstrated warm gain. Existing snapshots already bypass extraction.

All twelve edit validations pass: unchanged, comment-only change, test rename,
test addition, module addition and restoration, on both engines. They verify
the expected check keys independently and compare complete output between
variants. No edit-latency improvement is claimed. Application check execution
was not benchmarked in this experiment.

The complete containerd archive test package passes, including new tests for
parent replacement, symlink aliases, whiteouts, hardlinks and custom callbacks.
A subsequent run inside a privileged benchmark container enables `-test.root`:
both overlay suites and extended-attribute tests pass, with no skipped tests.
These tests support correctness of the experiment; they do not establish a
discovery performance benefit or replace upstream review of its callback API.

## Decision and evidence

Do not enable this patch in the Dagger branch on the strength of these results.
It offers a small isolated extraction gain, with no established benefit to
the user's complete listing. The same quiet cold runs still spend about 10.6 s
and 5.0–5.2 s in the two application Go builds, and 1.1–1.6 s in each of two
TypeScript runtime calls. These spans can overlap other work and are not
additive wall-time savings.

The [evidence directory](collections-qa-performance-data/tar-parent-cache/)
contains the disabled patch, repeat scripts, exact cold and edit output,
profile summaries, compact host samples and tests. Large raw profiles and
executables remain outside Git, with their hashes in `provenance.json`.
Every engine created for this experiment is stopped; its volume is retained.
All twelve exceeded the 10-second Docker stop deadline and exited with code
137. That shutdown occurs outside the CLI timing. Equalizing this step removes
the lifecycle imbalance but does not guarantee that pending host writes have
finished; the pressure samples remain necessary.
