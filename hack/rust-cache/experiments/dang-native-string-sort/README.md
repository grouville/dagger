# Native string sorting: complete Go listing experiment

See [the report](../../NATIVE_DANG_STRING_SORT.md). Four measured pairs return the same 4,398 rows and exit successfully. Medians are 48.06 → 45.98 seconds; three pairs improve and one regresses. The candidate remains unselected and requires a provisional Dang builtin unavailable on stock beta.15.

The archive includes both module variants, the typed native implementation and tests, pure library test overlays, the complete controlled-engine overlay inventory, every timing attempt, profile chunks, CPU/allocation captures, source identities and native-cache retention checks. Go files are below testdata to avoid introducing build packages.

The profile captures are diagnostics, excluded from timing claims. Their CPU windows extend into maintenance after command completion. pprof's source-line display must use the compiled overlay: the absolute checkout may differ. In particular, clientSpans.ExportSpans line 938 is the resource encoder in engine-overlay-manifest.json's telemetry.go replacement.

Large text evidence is gzip-compressed with original sizes and SHA-256s in archive-manifest.json. The merged wcprof file is reconstructible from the raw chunks; it and the engine executable are omitted with hashes. No databases, snapshots, credentials, targets or Git metadata are included. Drivers describe local absolute paths that must be adapted to reproduce elsewhere. No PR is opened.
