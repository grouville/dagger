# Storage follow-up: normal fsync is mostly data writeout/wait

This is another **diagnostic checkpoint, not a performance fix**. No engine or
module implementation changes are activated. The earlier 8.765s/1.442s tail did
not recur, so its cause remains unproven. All earlier observations are retained.

The evidence now supports testing writeback ahead of the final content commit,
while preserving both final file syncs, directory sync, verification and resource
ownership. No saving is promised: an earlier syscall can block and merely move
the wait, or interfere with unpack/Cargo. The whole flow must improve.

## Six ordinary Rust flows with buffered storage sampling

The same frozen diagnostic engine/CLI/module ran ABBAAB gzip/zstd, three
independent pairs. CLI-managed fresh engines, original workload, real external
dependency upgrade and all invalidation gates are unchanged. A new read-only
100ms sampler covers the Dagger and native first commands, then stops before the
warm loop. It validates exact container identities and the engine volume's
backing device, reads host/device/cgroup counters, and keeps records in RAM until
both first-command timers finish. No cache flush, host setting or durability
change. Device counters include other activity; partition/parent are not summed.

Sampler costs are observable: 294–351ms of sampler-thread CPU over each roughly
19–20s first-command pair, plus startup discovery subprocesses not included in
that CPU number. Individual collections took at most 5.6ms; maximum sampling gaps
were 241–272ms during discovery. These are diagnostic cold timings, not an
unprofiled headline or measurement of the sampler's wall-time overhead.

`storage-flow-results.csv` retains all 72 flow observations. Three repeated warm
observations per run are not nine independent pairs. Per-run warm medians are
summarized across the three runs; overhead is a median of paired differences,
not subtraction of marginal medians.

| Flow, zstd arm | Native median | Dagger median | Paired overhead median |
| --- | ---: | ---: | ---: |
| First check including ordinary CLI provisioning | 6.830800s | 11.761100s | +4.930300s |
| Exact unchanged | 0.122617s | 0.510306s | +0.385955s |
| Application edit | 0.294748s | 0.891223s | +0.601171s |
| Workspace-library edit | 0.460414s | 1.062362s | +0.595468s |
| Actual bstr 1.12.0 → 1.13.0 upgrade | 1.695649s | 2.315673s | +0.544761s |
| Unchanged after upgrade | 0.118127s | 0.527335s | +0.409207s |

Every median still loses to native. Cold zstd CLI range: 11.703484–13.084067s.
Compression's paired whole-CLI differences were −340.520, +933.991, +1269.611ms:
median +933.991ms, favorable 2/3. Rust delivery envelopes improved 410–456ms in
these three pairs, but Cargo and other phases also varied. Do not attribute the
entire CLI delta to compression or pool this with earlier cohorts.

All 36 wcprof captures passed, no rejected/open/dropped spans; all 18 cache,
36 crate-rebuild and 54 ordinary-execution audits passed. Failures, repairs, old
snapshot revisits and restart exact reuse retain their expected outcomes.
Both decoded OCI tar streams and image config are identical; exact compressed
layer bytes were transferred inside first use. All six disposable resource
groups and the owned registry/volume were removed; old container inventory was
restored. The collector/analysis passed 22 focused parser/ownership/lifecycle/
coverage tests. Kernel tracing was not running during this cohort.

`storage-sync-results.csv` records all 12 layer preSync intervals and their counter brackets.
Final-layer preSync 146–166ms brackets show roughly the compressed blob's bytes
written by the engine cgroup. Parent-layer preSync: 13–32ms. Counters bracket
100–302ms, often much longer than a sync: they do not assign every bracket byte
or flush to that file. No multi-second stall was reproduced.

Scope remains local prepopulated registry, preinstalled Docker/CLI/engine/native
image/module, fresh engine/CLI/Cargo caches, native through docker exec, matching
Rust 1.97.1 minimal+rustfmt and pinned ripgrep. This is not complete onboarding,
bare-host Cargo, artifact export, fmt/clippy/test, macOS or remote validation.

## Separate, inode-matched kernel diagnostic

After all Rust-flow captures/analysis were terminal, an approved bounded kernel
capture targeted the retained diagnostic daemon PID AND cgroup AND filesystem.
Journal/block events were restricted to its filesystem/backing physical disk.
No file contents, filenames, request addresses or commands were captured. Output
was buffered in RAM; the tracer detached automatically. No permanent privilege
or security setting changed. Both known Rust blobs were absent beforehand.

A single profiled public-image `Container.from(...).sync` query then materialized
the same gzip Rust image. The engine was prestarted to bind its PID: this is
image-only diagnosis, **not a new first-use Rust workflow score**. Query wall time
was 12.508343s; wcprof root 11.791220s. Existing CLI configuration also logged an
unrelated OAuth refresh 401, so startup/tail are not a clean-CLI comparison.

After the query, stat of only the two known blob digests verified device, size
and inode. Successful content commit renames the ingest file without changing its
inode. Each blob had exactly two successful, source-ordered kernel fsync calls:
preSync before the metadata transaction, then the existing local Commit sync.
Entry/exit counts and emitted records agree for all 21 parent syncs, 21 data calls,
17 journal-complete calls, 17 journal-wait calls and 4 flush calls. No orphaned child
or re-entry was found. An independent linkage audit checks initial absence,
engine identity, both distinct inodes, process success and trace hashes.

| Gzip blob | Kernel preSync | Inside data writeout-and-wait | Journal completion |
| --- | ---: | ---: | ---: |
| 28,232,590 bytes | 22.993439ms | 21.612459ms (94.0%) | 1.350436ms |
| 288,641,068 bytes | 174.703865ms | 172.869186ms (98.95%) | 1.819945ms |

These are wall intervals inside `file_write_and_wait_range`, not measured device
service time. `kernel-content-phases.csv` also includes the second, much smaller
file sync. Nested journal wait/completion intervals overlap; do not sum them.
wcprof wrapper durations differ from kernel durations by 0.0108–0.0613ms.

Only this narrow content-phase finding is accepted. Other evidence is limited:

- Four BPF map-initialization EEXIST warnings affect shared block aggregates.
  Those counters are **rejected**, not silently repaired. Generated IR shows a
  failed insert does not retry the increment. No device service-time claim.
- Installed bpftrace emits BOOTTIME, whereas the first runner recorded
  MONOTONIC anchors. Absolute cross-clock alignment is **not accepted**. Blob
  inode, two-call source order and intrinsic durations establish the narrow
  matches without converting clocks. Future captures must record BOOTTIME.
- wcprof structural completeness passes 61/61 engine spans, but replay drift is
  -6.9%. Its what-if savings are **not accepted**. Actual recorded intervals are
  kept separate from simulator predictions.
- This one normal ~175ms sync does not explain or eliminate the earlier 8.8s
  tail, establish device health, or prove an upstreamable speedup.

## Reproduction boundary and retained evidence

The parent README describes runtime ancestry, source-built tests, workload and
non-turnkey public reproduction limits. No raw telemetry, private analyzer,
credential or privileged executable is published here. Local controllers are
frozen and refuse to overwrite their results. To repeat locally, use a new owner,
the same image/CLI/module/source pins, rerun preflight, then:

```text
run-pairs.py --execute
analyze.py COHORT
audit-ordinary.py COHORT
commit-summary.py COHORT
phase-summary.py COHORT
summarize.py COHORT
analyze-storage.py COHORT
```

These owner-specific scripts remain local; the command sequence is an audit
recipe, not a claim that this public branch contains an executable full demo.
Kernel phase capture separately requires verified live probe schemas, exact
owned daemon/cgroup/device, bounded maps/time/output, completion/loss audits,
known blob inode mapping and a fresh image state. A prestarted diagnostic must
never replace the ordinary CLI-provisioning benchmark.

Provenance, SHA256:

- Counter controller: 15f1844f979315574cd16d1186a7e6fb00a48b76b21b4533e49b468278762d7c
- Counter sampler: 4ca045ea45f075bd0526e0b658cf3af88392d2fa46956aa4e197d13351b34c31
- Counter raw OTLP, 43,283,147 bytes: 3a0aab40db65e72544e2dfa2184926cef1a7d1a0a12f1bcc89ec59710620f209
- Counter wcprof/cache/crate report: ac781fce2046d6e4888be33bfa492a1e098367a9df5fa7f6d8617e7d7363e776
- Counter ordinary audit: aafb5cdddd2cc396c034569da8ecf852ed32914beb3719c01f51f8392cf78aac
- Counter summary: 1205a32cc619bf03ba85a9d3d6d6a762ad8f7dd6aa479b41aa2655cee50ca93c
- Counter storage analysis: f0f6da499e6219e2acc9a35062d1c14c63761145ba08d9e52a2c5c2a3fb60465
- Kernel events: 16cc83f867452ad64e7c8aef871dc472e0e301127b35c9202b69ff442aa92f33
- Kernel content analysis: f5a7f3a66cb16ee9d20b12ce4d3a5860a99c661420511fc7ed6899b965c00fbf
- Kernel independent linkage audit: 5ca466ed6d15f331ae781ed0810296383bcab1579ff6233044fd2504894b8125

Next experiment: bounded writeback-ahead on already-written content ranges,
retaining final durability and errors. Evaluate transfer/apply/commit and the
whole user flow, including Linux/non-Linux fallback and cancellation/partial
write correctness. In parallel conceptually, prepared/flattened ordinary OCI
toolchain delivery remains the larger vertical hypothesis; no net gain yet.
