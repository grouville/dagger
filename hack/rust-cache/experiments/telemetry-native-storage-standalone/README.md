# Standalone native telemetry storage patch

See the [assessment](../../NATIVE_TELEMETRY_STORAGE.md) and [proposed description](../../PR_ENGINE_NATIVE_TELEMETRY_STORAGE.md). The fork branch is `perf/native-telemetry-storage`, commit `24413663907fe2cbe03e3c68740541ab5f591f80`, based on upstream main `ff0b029a4d270a651b9a8c7286babc79089066e4`. No PR is open.

`evidence.tar.gz` contains the exact patch and before/after sources, validation drivers and logs, two expected failing regression controls, and four alternating component pairs. `MANIFEST.json` records the verified size and SHA-256 of all 61 members. Drivers and overlays retain their original absolute paths; adapt those paths for replay. No engine binary, credentials or cache volume is included.

The standalone patch adds a durable version-header upgrade beyond the measured prototype. Its migration latency is unmeasured. Full-command timings remain in the two separately retained controlled-engine cohorts; this archive does not claim a new end-to-end measurement or replace the running engine.
