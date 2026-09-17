# Why a cheaper mount does not give the same saving to consumers

2026-09-17. Diagnostic follow-up to RESULTS.md, not a production engine change.
The upstream composefs tools, Ruff revision and CAS base are unchanged.

## Isolating first access

`TestComposefsReadProbe` reuses verified immutable results from the original
matrix. Four alternating rounds compare the direct CAS result, a generic
read-only overlay over that directory, and native composefs. A raw EROFS image
is a metadata-only control, not a usable replacement: its payloads live in CAS,
and its 256 internal whiteouts are hidden only by the composed view.

The common expected-input capture warms the backing data before timing. The
overlay and composefs mounts are fresh. These probes measure the cost of first
access to a new view, not cold disk or full filesync. The byte-reading probe
uses known paths, one shared buffer and content-digest checks; it excludes
directory enumeration. A complete semantic check also runs outside its timer.

Medians in milliseconds, four samples each:

| Work | Direct CAS directory | Generic overlay | Native composefs |
| --- | ---: | ---: | ---: |
| First metadata walk | 46.02 | 84.85 | 116.76 |
| Second metadata walk | 45.39 | 56.25 | 50.56 |
| First known-path read, including hashes | 124.26 | 186.25 | 241.41 |
| Of which opening files | 63.53 | 111.99 | 162.83 |
| Of which bytes + hashing | 32.69 | 36.91 | 38.65 |
| Of which closing files | 10.33 | 16.92 | 17.91 |
| Second known-path read, including hashes | 121.25 | 146.70 | 148.05 |
| Unmount without reading anything | — | 0.10 | 1.57 |
| Unmount after read probe and semantic validation | — | 10.34 | 32.90 |

Totals also include path construction, hash initialization and comparison.
Phase medians are not additive. Per-file clocks add diagnostic overhead.

The excess first-read cost is mostly opening paths, not reading payload bytes.
After the first pass composefs is close to the generic overlay control. This
supports first-access metadata/path resolution as an important cost; it does
not identify an exact kernel function without kernel stack samples.

Unmount is not a fixed 30 ms delay. It rises after populating the filesystem's
cached objects. The read and walk probes both run full semantic validation
before unmount, so their unmount values cannot isolate metadata-only teardown.
Moving unmount into the background would not remove this work.

## Benchmark correction, not an engine speedup

The original full verifier allocates about 405 MB per pass (27–28 collections):
`io.Copy` allocates a buffer for each regular file, and per-entry test assertions
add bookkeeping. The known-path diagnostic uses roughly 21 MB and 2–3
collections, but does less work, so its time must not be substituted for the
full verifier's time.

The revised full verifier retains every path, digest, ownership, mode, size,
mtime, symlink and hardlink-group check. It shares one copy buffer and reports
errors at the boundary rather than invoking assertion helpers for every
successful operation. Composefs admission/encoding likewise checks errors
without per-entry assertion helpers. This corrects test overhead in both
consumption arms and in the prototype's composefs-only preparation loops.
No production CAS code or upstream filesystem implementation changed.

The original RESULTS.md and its evidence remain intact. A new full matrix is
reported separately; lower absolute numbers from this correction are not an
optimization delivered to Dagger users.

## Corrected full comparison

Four alternating paired rounds, profiling disabled, same seven fixture states.
All 56 Ruff samples and the tiny semantic fixtures passed. Median milliseconds:

| State | CAS ready | composefs ready | CAS ready + first full read + release | composefs same | Median paired saving |
| --- | ---: | ---: | ---: | ---: | ---: |
| Empty CAS | 928.51 | 878.01 | 1119.06 | 1218.05 | -104.47 |
| Unchanged, forced materialization | 370.29 | 135.78 | 567.48 | 482.97 | 84.55 |
| One-file edit | 361.96 | 136.71 | 550.92 | 478.92 | 72.00 |
| Directory move | 373.19 | 135.15 | 562.26 | 475.82 | 82.32 |
| Mixed diff | 369.80 | 151.05 | 557.96 | 508.92 | 52.18 |
| Broad reorganization | 367.55 | 139.66 | 558.39 | 488.75 | 67.96 |
| Repeat edited tree, forced materialization | 375.48 | 135.93 | 571.92 | 482.22 | 89.70 |

The one-file result becomes ready 2.65 times faster, but its consumer-inclusive
component sum improves only 13.1%. All four warm pairs in every row improved;
all four cold pairs regressed. The one-file paired saving ranges 50.37–89.15 ms;
cold regressions range 79.39–180.46 ms. As in the original matrix, release is
measured after two reads and added to the first-read sum, not executed in a
separate single-read trial. No teardown cost is hidden.

One-file phase medians: CAS copy/publication 361.91 ms; composefs admission
39.34 ms, encoding 41.81 ms, image creation 52.19 ms, mount 3.22 ms. First full
verification costs 189.62 versus 313.32 ms; second 177.87 versus 213.63 ms;
composefs unmount 29.21 ms. The two-read wall interval is 728.02 versus 692.08 ms.

This remains a materialization experiment, not main-versus-branch CLI or Cargo
latency. Cold source data is warmed by common input capture. Unchanged rows
force work a complete-result cache hit normally avoids. The report's CAS arm
is the existing experimental CAS implementation, **not main**.

Raw evidence: `/tmp/dagger-composefs-read-cost.0CFlKUEv/corrected-matrix-r1`.
Its generated RESULTS.md reports ready + read **without** release; the table
above uses `ready_first_read_release` from the retained per-sample JSON instead.
The temporary container was stopped successfully and all files retained.

## What is worth pursuing

1. Measure the actual compiler's access pattern. Reading every fixture byte is
   deliberately conservative, but is not Cargo. A sparse consumer might retain
   more of the materialization saving; repeated whole-tree access erodes it.
2. Attribute the remaining preparation work (CAS checks, metadata encoding,
   image creation). Removing redundant work here helps without a filesystem
   fork. Do not skip object lifetime or content verification.
3. Reuse a mounted immutable result when its normal engine lifetime permits.
   This can amortize access/teardown for repeated consumers of that result;
   it does not eliminate first-access cost for every newly edited tree.

Changing the payload CAS alone will not remove the measured overlay lookup
cost. A new snapshotter, a custom filesystem or asynchronous cleanup is not
justified by these probes. A twofold consumer-inclusive gain is not established.

## Evidence and reproduction

Evidence: `/tmp/dagger-composefs-read-cost.0CFlKUEv/probe-r3` contains 52 passing
samples and 52 wcprof analyses. `probes.py` in the parent contains the local
orchestration. Earlier failed controls are retained separately (single-lower
overlay rejected by the kernel, then raw EROFS's extra whiteouts).

Compile with the same `composefsbench` tag described in README.md and run
`TestComposefsReadProbe` in a private mount namespace. Environment:

```text
COMPOSEFS_READ_BASE    retained immutable CAS result directory
COMPOSEFS_READ_ARM     cas | overlay | composefs | erofs
COMPOSEFS_READ_MODE    none | walkstat | read | original
COMPOSEFS_READ_OUT     new diagnostic output directory
COMPOSEFS_READ_CACHE   composefs payload store
COMPOSEFS_READ_IMAGE   retained tree.cfs
COMPOSEFS_BENCH_MOUNT  upstream mount.composefs executable
```

`original` means the full semantic verifier in the compiled test binary. The
recorded 52-sample probe used the original allocating verifier; recompiling
after the benchmark correction changes that mode, not the known-path reader.
Raw EROFS accepts only `none` and `walkstat`. No shared engine is touched.
