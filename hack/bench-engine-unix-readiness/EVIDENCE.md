# Completed local evidence

Measured owner: /tmp/dagger-unix-readiness.UfjY9dsi.
Cohort: /tmp/dagger-rust-unix-readiness-ab-dda1zn80.
Publication is a separate checkout; measured sources/controllers remain frozen.

| Original local artifact | SHA256 |
|---|---|
| Before-test log | 1ca5712c0fcdc182c45c25839cf4221b022657074c0e794753066bb124d21d2b |
| Before-test inputs | ce1576fbf01474c71fbab523e4646aa6c910d964dba3f12e7f0d50e386898328 |
| Supported build manifest | 4036040ebb38da27739225fdf2ab13183065ac4868e198dd7aaf4b8c0a00db54 |
| Docker lifecycle record | 8be76102055593e57e3afb41712b4e76da9bf60d629c2445311d35e8f75d384f |
| Raw OTLP, 43,191,744 bytes | ef5b747bcbcd9e927dacf1925ac41f93b2cab5fd339e314aa894b7e27245eea8 |
| Full summary | 23ae7a65aee09da54aaa0d960cb0a1084434051fc474372519e760fe9ffa6c65 |
| Full cold phases | f157759e9bd061fbbb934e243d7257b36e7d2a73b31e52f24011dd1191c1107f |
| Full wcprof report | 2b9098f02506c6eaa76e53c0742d6b07bda1199b300b80e25c77deaa39970ef6 |
| Ordinary-execution report | c7a0fa1aa395490045e07163ca811d72f1f520b4e58e56350162f28d5f69d19f |
| Full post-capture warm diagnostic | fd8f75becc06e53146958d5d5c3aea1bc7227f0a32fc4050d96691f2a92c6078 |
| Restart-outlier engine log | e3d26ac21e2a0071cfa19d44e03c5b66ed9829ca70327b3ea3784365ae479dbf |
| Publication race-test log | 7e9797f72477af4fcb873ff26a527c94aa3d703f82f3a4d703d8085f0665e687 |

Process handles independently completed:

- Negative reproduction 18021: exit 1, expected immediate missing/refused errors.
- Initial local race test 30445: exit 0, 6.633s; precedes the two test-hardening edits.
- Supported final test/build 95707: exit 0; race/count3 selection, deploy and query pass.
- Real Docker lifecycle 54931: exit 0, both cases pass.
- Full workflow 95851: exit 0, six runs pass.
- wcprof analysis 29513: exit 0; explicitly checked all 36 profiles,18 caches,36
  affected-crate comparisons and zero rejections, not just the analyzer exit code.
- Ordinary execution audit 69461: exit 0; explicitly checked all 54 actual timed
  command audits. Summary and phase contract also pass.
- Publication source race test 86443: exit 0, 6.603s; exact helper/test file hashes
  match the supported built source.

All 2922 capture-recorded source/controller/tool hashes were checked again after
the full run. Each cold consumes the full 316873658 compressed Rust bytes. Native
and Dagger select the same affected packages; correctness gates are scoped to the
recorded workload, not all Rust configurations.

All six cleanup records report their native container, engine container and
engine volume removed, with no errors or retained resources. Their exact names
were independently queried afterward and absent. Fixture roots end in
ufzvxzgj, tua2xqs1, vrm8vltl, j02xprcr, h1xeznx4 and fvfqlogi.

The receiver PID 2088916 exited -15 during normal teardown and was independently
absent. Retained engine IDs 8ad9acfed096 (control) and 657d148b90b1 (candidate),
images 1fb356/5d6602, and restart counts 0 stayed unchanged. Their images/caches are
kept for follow-up work; no user engine was deleted. The stable 59-container
unrelated inventory is recorded only as count/digest in public evidence, not names.

Public results retain every headline measurement, including the native outlier
and all warm losses. Compact gate/phase documents omit raw span records and
attributes. The warm diagnostic publishes per-run medians and the script; the
full 84-trace-derived local document is hashed above. No raw telemetry, private
analyzer source/binary, OCI image or unrelated inventory names are included.

The 2-B restart log evidence is second-resolution engine logging, correlated with
nanosecond Info spans. It localizes most delay before listener readiness but does
not identify a precise blocked engine subsystem or rule out helper timeout/retry.
Follow-up must investigate the initialization delay and observed small warm
connection losses; these are not silently classified as harmless noise.
