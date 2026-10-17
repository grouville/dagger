# Go listing: prepared declarations

See [the report](../../NATIVE_DANG_REUSABLE_DECLARATIONS.md). This is an opt-in prototype, not an upstream PR. The selected Go implementation is unchanged.

`source-manifest.json` identifies the exact overlay files. Engine base: `19eda924854e7f22582f3a7430272aa729cbeb5f`; Go module: `b5dd9434a52972787171a016a8aa9d8910c17c38`; repository fixture: `ff0b029a4d270a651b9a8c7286babc79089066e4`. Absolute paths in the original drivers identify the diagnostic environment and must be mapped when reproducing elsewhere. The module delta directories preserve changes against Dang v2.1.4 and containerd v2.2.5; the engine modfile records exact replacements.

`full-command-pilot` and `full-command-reverse` contain opposite run orders, fresh edits, all rows, engine GC events, heap samples and exit status. `known-input-full-pilot` tests the independent ID shortcut with declaration reuse off. Profiling is diagnostic and excluded from clean latency results.

The first recipe-only ID prototype panicked; engine recovery deliberately cold-started its query cache. Its errors and the native history restoration are retained. Successful comparisons use a new baseline on that recovered engine. They cannot establish a speedup against the earlier engine cache state. All six native Rust histories were subsequently restored and verified, then preserved across a graceful engine replacement.

No engine binaries, database files or private metadata database copies are included. Both experimental modes are restored off after each driver.

Archived Go sources and module deltas are under `testdata` so they do not become packages in the parent repository. Original source bytes and hashes are preserved.
