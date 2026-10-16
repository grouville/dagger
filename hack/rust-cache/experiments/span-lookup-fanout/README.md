# span-lookup-fanout

See [the experiment report](../../NATIVE_SPAN_LOOKUP_FANOUT.md) for results, disposition and limitations. `runs` retains test logs, component and full-command data, fresh edits, pressure, profiles, source files and runtime settings. Binaries, volumes, target directories and Git metadata are excluded.

The engine source base is `19eda924854e7f22582f3a7430272aa729cbeb5f`. `engine/source-mirror.json` records uncompressed SHA-256 hashes and archived paths relative to this experiment. Unchanged overlays reference the already committed `artifact-metadata-fields` archive; changed files are mirrored locally. Check both archives when reconstructing the engine. Raw overlay and dependency files retain local absolute paths and need adjustment when rerunning.

Complete command benchmarks use warm compiler/engine caches, a fresh used source edit and CLI process, telemetry enabled, ordinary GC and no forced collection. Instrumented captures remain separate from timing cohorts. The selected baseline and whether an upstream branch is prepared are recorded in the report. The native Rust-cache goal remains incomplete.
