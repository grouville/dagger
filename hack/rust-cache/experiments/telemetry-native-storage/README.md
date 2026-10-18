# Native telemetry storage: correctness, components and full Go listing cohort

See [the assessment](../../NATIVE_TELEMETRY_STORAGE.md). These archives retain exact sources and overlays, drivers, diagnostics, every test outcome and any component observations. This prototype reduces CPU and allocation in all eight pairs and improves the full listing median in its first cohort. Native writing remains disabled pending an independent-order confirmation and migration review. The engine keeps dual-format readers and outer-store v2 support; do not downgrade to a v1-only reader over these telemetry stores. No upstream-ready proposal or PR is claimed.

`MANIFEST.json` records the size and SHA-256 of each independently verified archive member. Engine binaries are omitted and identified by build hash. Expanded recorder data is reconstructable from the compressed chunks.
