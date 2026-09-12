# Results: local-registry packaging, not public first installation

All times below are milliseconds. A is base image plus runtime preparation;
B is prepared image with the same normal root-config handling. Both use the
same experimental engine, fixed CLI, native comparator and real ripgrep
fixture. First checks are wcprof-profiled. Cargo HTTP logging is disabled in
both cohorts below. Network and compiler variability are retained.

| Cohort | Pair order | A full CLI | B full CLI | Paired saving |
| --- | --- | ---: | ---: | ---: |
| Original | AB | 12627.310 | 12694.964 | -67.654 |
| Original | BA | 12431.343 | 12630.675 | -199.332 |
| Original | AB | 12685.499 | 12063.650 | +621.849 |
| Confirmation | AB | 12841.831 | 12374.684 | +467.147 |
| Confirmation | BA | 12414.087 | 11880.983 | +533.104 |
| Confirmation | AB | 13532.683 | 11637.389 | +1895.294 |

Original paired median: -67.654 ms, one of three favorable. Confirmation:
+533.104 ms, three of three favorable. Across all six pairs: +500.125 ms,
four favorable, range -199.332 to +1895.294 ms. Separate cohorts represent
different time windows, not one simultaneous randomized experiment.

Paired overhead reduction versus each native run is 263.525 ms median,
259.837 ms including engine provisioning. Do not describe the 500 ms CLI
improvement as a 500 ms reduction relative to native execution.

| Phase | Median paired saving over all six pairs | Favorable pairs |
| --- | ---: | ---: |
| rsync package installation | +191.080 | 6/6 |
| root-config rustup preparation | +660.396 | 6/6 |
| image delivery/unpack envelope | -84.718 | 1/6 |
| Cargo/source reconciliation | -308.872 | 1/6 |

Phase medians must not be added as if they described a single run. The large
last-pair CLI improvement includes Cargo variation. Cargo's adverse pattern
is unresolved, not discarded as proven random noise.

## Image and correctness evidence

Original two base layers are unchanged byte-for-byte, including diffIDs.
Base compressed image size is 316,873,658 bytes; prepared is 320,449,193 bytes:
an increase of 3,575,535 bytes (about 1.1%). Prepared layers add rsync/libpopt
and rustfmt. Their inventory contains no project/target/registry/git cache.
Compiler, Cargo and native C-compiler versions match.

Each cohort passed 30 complete wcprof capture/count/actual-exec/image-progress
gates and 18 post-timer cache analyses: 60 profiles and 36 cache analyses total,
zero rejected runs. Actual base/prepared layer-byte sets match their expected
descriptors. App/library changes, selected package/version parity, intentional
compile failures/repairs/revisits and engine-restart exact reuse passed. The
last pair of each cohort also passed component/config add, invalid, repair
and removal checks. These do not substitute for full Rust workflow coverage.

An intervening four-run HTTP diagnostic was intentionally excluded from the
timing pool because logging changes execution and telemetry costs. It passed
20 wcprof gates, 12 cache analyses and four independent HTTP/runtime-identity
gate sets. Both native and Dagger made 52 index and 34 crate fetches, receiving
86 HTTP 200 responses. Cargo, linked libraries, CA/config/lock/toolchain and
diagnostic environment matched. Both Dagger variants had identical loader
caches; native's differed because it did not install rsync.

That diagnostic did not establish a large DNS/TLS penalty. Delay remained
after response headers, which does not distinguish response bodies, scheduling,
verification, extraction or logging. Four parser tests covered exact-exec
split-line attribution, secret/header suppression and missing/unknown evidence.
Raw HTTP logs are deliberately not published.

## Limits and reproduction validation

This is Linux/amd64 on one host, local unauthenticated OCI registry, public
Rust/Cargo services, fresh engine/CLI/Cargo states. Registry and host page
caches were not purged. Native always followed Dagger within first-use samples.
Docker, CLI, engine image, module and native Rust image were preinstalled.
The common engine contained the experimental pipelined-hash dependency; this
branch neither vendors nor ships that dependency change.

Confirmation B provision plus check was 12,108.089 ms median; its per-run
overhead versus native was 5,208.529 ms median. Those local-registry numbers
must not replace the separate public-route overhead of approximately 9.7 s.
No complete-installation, artifact/fmt/clippy/test-command, external-library-
upgrade, macOS or remote-engine performance claim follows from these cohorts.

Both source modules match the measured bytes. The published statistics script
reproduces the retained paired results. The image builder compiled against
the clean-main Go SDK and completed a normal `dagger api with-session` export
on the retained hash engine. Both entire OCI tar files match the original
artifacts byte-for-byte:

- Base SHA256: `8b9c8837d7b4ecce07ad64e0cf0cda5ee273bf7cf2d80ec58bff54491d935be7`.
- Prepared SHA256: `f4233b6ca8f2089c953cd9aa3084406813951f924514e7231713312d5921f397`.

Missing output argument, existing artifact and nonexistent directory all
failed before connecting/exporting. No prior files were overwritten. This
validates the helper interface/recipe, not a new cold measurement. The export
run emitted migration warnings about root dagger.toml SDK fields; its log is
retained rather than described as warning-free current-main engine validation.
Session 57328 exited successfully; no image was published to a registry.
