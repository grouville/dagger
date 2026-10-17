# Parse workspace TOML once

See [the report](../../NATIVE_WORKSPACE_SINGLE_TOML_PARSE.md). Four complete matched pairs do not establish a reliable listing improvement, despite clear parser CPU/allocation gains. The experiment remains disabled and no PR is opened.

The standalone patch reuses one parsed document for the existing decoder and field validation. It introduces no memoization, skipped host reads, policy changes, lock or dependency. A/B controls are excluded from the standalone patch. Original and candidate tests, race checks, component benchmarks, every full command, engine source, restart/retention checks and restored state are retained.

Large text captures use gzip. archive-manifest.json verifies original and archived bytes. Raw Go files remain under testdata; no database, native snapshot contents or Git metadata are included. The executable is omitted with its SHA-256 and build command. The unchanged pinned telemetry SDK and shared modfile are identified by ../otel-evicted-queue/. Drivers contain local paths requiring adaptation.
