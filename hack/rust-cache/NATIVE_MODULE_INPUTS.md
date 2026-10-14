# Native inputs for the Rust module

`replay.BuildNativeAutomatic` takes the module's source and previous cache as
native `Directory` objects. It returns the existing graph's `Artifacts` and
`History` directories. Compiler outputs and rustc incremental state remain
immutable native Dagger cache; no compiler cache volume is introduced.

`replay.BuildNativeCached` uses the same compiler and result-selection logic,
but returns `Graph.Cache`: a manifest string and a list of immutable batch
directories. Retaining these fields avoids copying each new batch into a
combined history directory. Removing an expired batch from the list also avoids
constructing a filesystem snapshot solely to prune the history archive.
`Graph.History` is nil with this entry point. A module must retain the native
directories themselves; serializing their local IDs is not a portable cache.

The source must already exclude `.git` and `target`. The builder reads only
Cargo manifests, lockfiles, toolchain files and `.cargo` configuration into the
client to validate the captured plan. It hashes and mounts the actual native
source directory for compilation. It does not require a host copy of every
source file or trust a separate source map to represent the module input.

The full `TestRemoteCacheTransferSuite/TestRustCompilerReplay` integration
scenario passes through this entry point for all batch builds. It checks a
changed native configuration, fresh source edits, exact result reuse, bounded
manifest history, undeclared dependencies and source reads, and an edit after
transferring history to a second fresh engine. The old builder remains available
for the standalone driver's host-input experiments.

The same integration test covers object-cache edits, exact reuse after reverting,
and removal of expired batch references. It transfers the manifest and retained
snapshots to a second fresh engine, reconstructs the object cache using the
imported directories, and checks exact hits and a new dependency edit there.
This proves that the representation transfers; a complete module object and its
automatic discovery are still to be implemented. It also does not establish
bounded physical snapshot ancestry or a command speedup.

This is the backend boundary for module integration, not a completed user flow.
The module still needs to capture/reuse plans, discover previous history, expose
the result, and select this backend for supported actions. Registry dependencies,
build scripts, procedural macros and Cargo tests remain unsupported. Published
artifact builds must preserve the Rust module's existing reproducibility policy;
its incremental compiler settings cannot simply be changed for speed.
