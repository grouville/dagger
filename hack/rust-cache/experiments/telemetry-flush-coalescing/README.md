# Session telemetry flush coalescing

See [the report](../../NATIVE_TELEMETRY_FLUSH_COALESCING.md). This is an opt-in prototype, disabled by default. No PR is opened.

Engine base: `19eda924854e7f22582f3a7430272aa729cbeb5f`. The engine overlay extends [the preceding declaration-reuse experiment](../go-dang-reusable-declarations/). Its source manifest and module deltas identify inherited sources. This directory contains the coalescer, diagnostic switch, exact modified session source, focused race tests, runtime checks and complete paired attempts. The absolute paths in the original drivers identify the diagnostic environment; map them when reproducing elsewhere.

`full-command-paired/samples.json` contains every timing, exit code, row check, heap sample and flush counter. Signals stay enabled. Both arms use declaration reuse. Both failed counter-export tests are retained alongside the passing gauge and lifecycle suite. No engine binaries or database files are included.
