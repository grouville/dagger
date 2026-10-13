# Native inputs for the Rust module

`replay.BuildNativeAutomatic` takes the module's source and previous cache as
native `Directory` objects. It returns the existing graph's `Artifacts` and
`History` directories. Compiler outputs and rustc incremental state remain
immutable native Dagger cache; no compiler cache volume is introduced.

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

This is the backend boundary for module integration, not a completed user flow.
The module still needs to capture/reuse plans, discover previous history, expose
the result, and select this backend for supported actions. Registry dependencies,
build scripts, procedural macros and Cargo tests remain unsupported. Published
artifact builds must preserve the Rust module's existing reproducibility policy;
its incremental compiler settings cannot simply be changed for speed.
