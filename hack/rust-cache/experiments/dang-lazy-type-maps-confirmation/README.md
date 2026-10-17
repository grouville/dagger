# Scope-map confirmation

See [the report](../../NATIVE_DANG_TYPE_MAPS_CONFIRMATION.md). The initial pair and the first measured pair are excluded; the latter may overlap an unintended broad file search. The exclusion was recorded before examining the remaining pairs. Every attempt is retained. The original unfiltered summary is kept as summary-all-attempts.json; summary.json and paired-analysis.json apply the exclusion.

No implementation changes or engine restart were needed. source-identity.json verifies the controlled scope-map source against the current binary's [complete engine overlay manifest](../otel-evicted-queue/engine-overlay-manifest.json). The [previous experiment](../dang-lazy-type-maps/) contains the pure library patch, full package tests, race result and component benchmarks. The candidate remains disabled, and no PR is opened.

Large text captures are gzip-compressed. archive-manifest.json retains both hashes and sizes; drivers contain local paths requiring adaptation elsewhere. Raw Go files remain under testdata. No database or snapshot contents are included.
