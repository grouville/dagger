# Package fingerprint experiment evidence

See ../../NATIVE_PACKAGE_FINGERPRINTS.md for interpretation. These are warm edited-command experiments; unchanged runs check correctness only.

The native fingerprint cohorts contain eight measured pairs each. The local-script cohort contains eight pairs; its confirmation stops during the first measured pair when idle admission times out. Keep all observations, preparation logs, partial output and failures.

Logs, raw telemetry and wcprof dumps are gzip-compressed. Use `gzip -dc file.ndjson.gz > /tmp/file.ndjson` before passing a dump to wcprof-report. CPU profiles are unmodified pprof files. Complete Cargo metadata output is retained in compressed logs.

The state probe uses temporary module copies with one root method returning `JSON.encode(packages(source: source))`. Neither measured branch contains that method. The .json files retain the resulting nested project objects.

The first native validation reused existing execution inputs. The unique validation adds a manifest nonce and verifies both execution counts and metadata hint publication. Initial full-reuse assertions after listing-only edits observe the expected two dirty actions; final strict reuse follows compiling those edits.

Harnesses reference the local fixtures and SDK/engine worktrees recorded in source-revisions.json and cohort metadata. The engine binary includes previously selected experimental overlays listed in native-package-fingerprint-engine-overlay.json. The standalone engine feature and each module variant are committed separately on the fork. No PR was opened.
