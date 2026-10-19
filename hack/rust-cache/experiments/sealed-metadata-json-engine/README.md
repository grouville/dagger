# Sealed metadata encoding experiment

**Not selected.** See the [report](../../NATIVE_SEALED_METADATA_JSON.md) for complete-command results and the pipeline requirements.

`assessment.json` records four measured pairs for each edit workload, functional gates and six successful diagnostic captures. `evidence.tar.gz` includes the raw samples, logs, source changes, component results and earlier contention capture. `manifest.json` records each member's size and SHA-256; every member was checked after compression. `archive.json` identifies the archive.

The archive contains:

- `standalone/candidate.patch`, production source and the separate new `engine/server/metadata_json_test.go`, based on the revision in `standalone/identity.json`.
- `antecedents/sealed-metadata-json/`, component benchmarks, focused checks and race results.
- `antecedents/go-glob-critical-path/`, the motivating contention capture.
- `engine-plan.json`, `engine-build.json`, `overlay.json` and `build-source-manifest.json`, exact development-engine inputs. Unchanged source is referenced by path and digest into the parent archive identified in `parent-source-archive.json`; five changed or additional inputs are copied under `source-delta/`.
- `test-edit-paired/` and `source-edit-paired/`, all command samples, source restoration records and resource counters.
- `checks.json`, `rust-pipeline/` and server race logs, behavior checks including real selected execution and native Rust action reuse.
- `capture-*` and `locks-*`, successful lossless wcprof streams, CPU profiles and analysis. The lock captures also retain before/after mutex and block profiles.
- `initial-missing-parallel-mode/` and `initial-admission-timeout/`, retained unsuccessful attempts, with explanations in the assessment.

The seven raw wcprof streams, including the antecedent capture, are retained as gzip chunks. `wcprof-reconstruction.json` records their exact reconstructed hashes and event counts; uncompressed duplicate streams and executable binaries are excluded. `archive.py` shows the reconstruction and verification procedure.

`final-state.json` verifies the eight retained engines, their binaries and volumes, source restoration and disabled diagnostic switches after the last capture. No PR was opened.
