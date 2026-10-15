# Constant scripts and cache usage allocation evidence

See [the engine result](../../CACHE_USAGE_ALLOCATIONS.md) and [the module experiment](../../NATIVE_CONSTANT_SCRIPT_STATE.md).

The engine feature is based on pinned upstream main and is not installed in the Rust timing engine. Its existing benchmark runs in fresh processes. One completed baseline observation was reused after correcting a parser for the benchmark's custom metric columns; no observation was discarded.

Both complete Rust cohorts contain eight measured pairs for each scenario. Admission includes CPU and I/O criteria fixed before those cohorts. All admitted observations remain included. Every invocation changes only its own used source value after admission. Listings require the exact expected 1,026-name set.

Logs and wcprof captures are gzip compressed. CPU profiles are original pprof files. Decompress a wcprof capture before using wcprof-report. CPU capture windows include the command and subsequent engine work; cumulative samples can overlap.

The state probe uses temporary module copies. Normalized JSON bytes and the runtime's literal JSON bytes are reported separately; run analyze_script_state_wire.py to reproduce the latter from retained logs. The measured branches contain no probe methods. Scripts and every non-script project field are compared for equality.

Final cache verification first prepares current source edits, including those performed only for listings, then performs a strict full-reuse pass. Unchanged commands are used only for correctness.

Local paths, engine state, source revisions and complete protocol settings are recorded in the harnesses and metadata. Fork pushes were authorized; no PR was opened.
