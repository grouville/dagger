# Native Rust cache performance

Make edited Rust builds with native Dagger caching approach native Cargo's
incremental build time plus 0.5 seconds for the complete command. Preserve
compiler results and incremental state as native immutable Dagger snapshots,
including reuse across engines.

Measure the complete Rust module command as the final performance target. Its
cache should be expressed as native Dagger objects, with compiler outputs and
incremental state carried by immutable directories. Standalone replay timings
are diagnostic evidence; integration into the module and its user workflow is
required before calling the work complete.

Use Erik Sipsma's Go cache experiments and engine PRs as references. Review the
actual changes, check which are already in the measured engine, and use CPU
profiles and wcprof's critical path to find remaining costs throughout the
stack. A faster microbenchmark alone does not establish a faster build.

Priorities:

1. Measure fresh leaf and shared-library edits in both large crates and many-crate
   workspaces, with native Cargo as the control. Keep telemetry enabled; local
   receiver measurements do not establish production Cloud latency.
2. Profile every layer: CLI and module loading, source import and hashes, graph
   construction, snapshot ownership and copying, mounts and container startup,
   compiler scheduling, cache retention and transfer, and telemetry. Reduce the
   work that delays the complete command. Validate each experiment with matched,
   alternating runs and correctness checks.
   Review algorithmic complexity and allocations in module loading, check and
   collection discovery, not only compiler actions. Compare alternative libraries
   on real inputs, including first-use cost and complete-command effects.
3. Preserve automatic incremental seed selection, compiled-result reuse and
   Cargo's overlap between dependent compilations. Never exclude compiler inputs
   from the cache key without proving correctness.
4. Measure storage and transfer costs on fresh engines, then extend coverage to
   real Cargo workspaces, build scripts, procedural macros and tests.
5. Integrate the proven design into the official Rust module and its normal user
   workflow. Users should not have to create one Dagger module per crate.
6. Expose package selection as a collection within the module and include its
   discovery, selection and execution costs in the performance target. Share
   Cargo graph discovery and compiler scheduling across selected items; avoid
   starting a helper or container per package. Compare selected-package commands
   with matching Cargo package selections, and whole-collection commands with
   workspace Cargo commands.
   Compare the official Go module's package/test dimensions with an isolated Rust
   module exposing the same selection levels. Measure discovery, selection and
   edited test execution separately, retaining the workspace batch as a control.
   Investigate the reported Go collection crash on `dagger/dagger`; distinguish
   an engine crash from excessive discovery work, cancellation and memory used
   by the profiling recorder. Keep the existing ancestor index enabled while
   locating work it does not cover.
   Combined Rust compilation and test discovery removes one helper invocation
   per package, but remains slower than the workspace batch. Batching Go module argument reads removes
   1,728 engine queries at 64 packages and improves 10/12 collection pairs; the
   ordinary workspace control is flat. Profile the remaining engine cost of
   argument fields and repeated schema preparation before changing them.

Keep useful engine fixes separate, with focused regression tests and an
adversarial review. Push experiments to Guillaume's fork; open new upstream PRs
only after explicit approval.

Current measurements, limitations and experiment details are in [README.md](README.md).
