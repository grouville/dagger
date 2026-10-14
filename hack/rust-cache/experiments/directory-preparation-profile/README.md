# Directory preparation diagnostics

Apply `diagnostic.patch` to engine commit `1770e627a` with
`git apply --unidiff-zero`. It records directory resolution, evaluation,
path validation, snapshot reopening, checksum calculation, parent-frame reading
and digest publication. It also records locks in the active
`engine/contenthash` package. It does not change hashing or locking behavior.

The first captures omit the final parent-frame read probe; the second captures
include it. The normal Rust commands use the bounded-parser library and runtime
diagnostics described in [the parser study](../../NATIVE_PARSE_CACHE_BOUNDED.md).

These are temporary diagnostic phases, not a production instrumentation PR.
The [findings](../../NATIVE_DIRECTORY_RESPONSE_FOLLOWUP.md) explain why neither
hash-lock changes nor the frame-read prototype is selected for Rust latency.
