# Go discovery follow-up evidence

Code: grouville/go perf/module-discovery, b5dd9434a52972787171a016a8aa9d8910c17c38. Baseline: perf/package-test-discovery, 9a1ea73ec6dffa72e3f450ea413ad93bc323ecd8. The clean real-repository checkout is dagger/dagger ff0b029a4d270a651b9a8c7286babc79089066e4.

- metadata-final: two balanced pairs of module-root and owned-file discovery, with exact output equality.
- collections-final: four balanced pairs per 1/16/64-package fixture, eight tests per package, with batch and native controls.
- many-files-final: four pairs for one package with sixteen test files.
- profiles-final: separate complete wcprof captures and timestamped five-second CPU windows on the final source.
- real-repository: bounded expanded-listing diagnostics. The final complete dump includes cancellation cleanup, not successful completion within 90 seconds.
- provenance.json, minimum-engine-compatibility.json, runtime-state-final.json: exact source/runtime context and restored modes.
- harness-notes.md: intermediate source versions, mixed timing controls, the slow GC episode and capture limits.

Read the report in ../../NATIVE_GO_DISCOVERY.md before interpreting the data. The engine is a diagnostic build with earlier selected optimizations on both arms; it is not unmodified upstream. Telemetry and ordinary GC remain enabled. Profiling is off for timings. Every timed arm changes source and starts a new CLI. The index-building cost is included.

Raw-source and compressed-artifact hashes are in manifest.json. Go source snapshots are under testdata so they do not add packages to the enclosing Go repository. The engine overlays are in ../interface-field-snapshots/; dependency context is shared with ../rust-go-test-collections/engine/. Executables, toolchains and compiler caches are excluded.
