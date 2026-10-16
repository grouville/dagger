# Test collection evidence

See `../../NATIVE_TEST_COLLECTIONS.md` for the findings and limitations.

`go-file-search-confirmation/partial-summary.json` contains the final 16-package
Go comparison. Its 64-package warmup exposed an unreliable TUI-row assertion;
the completed 16-package observations remain valid and are retained. The final
64-package comparison is `go-file-search-sixtyfour/summary.json`. Smaller
controls cover one package with one file and with sixteen test files.

`rust-correct-granularity/summary.json` is the final Rust comparison. The earlier
screens use the shared-workspace prototype, whose selected-package semantics
were incomplete. Their exact sources are frozen under `prototype-measured/`.

`profiles-final-sixtyfour/` records complete final execution profiles, with zero
open or dropped operations. CPU sampling covers five seconds; the metadata gives
the window rather than claiming complete CPU coverage for longer commands.
`profiles-sixteen/` captures the earlier implementation and the Go baseline.

The two real-repository diagnostics were cancelled at 120 seconds. The engine
remained running without an OOM. Late recorder drains are kept separately.
Only a stalled `docker logs` reader was interrupted after the final command had
ended; no engine process was terminated.

`manifest.json` maps original paths to archived files and hashes their
uncompressed contents. Large logs, profiles and source files are gzip-compressed.
Fixture target directories, Go build caches, generated SDK exports, Git metadata
and executables are excluded. `prepare.py` and the many-file fixture reproduce
the source layouts; adjust the recorded `/tmp` paths and pinned module checkouts
for another environment. Every fixture needs its own Git boundary.

`engine/source-mirror.json` records all 64 effective source overlays. Paths are
relative to this experiment directory, including references to the already
archived unchanged source files. The engine's overlay file retains its original
build paths; remap those to the recorded source base and decompressed mirrors
when rebuilding. `cli-provenance.json` records the exact shared CLI identity.

`branches.json`, the final patches and Rust worker-input hashes record the
published revisions. The Go change is prepared for individual PR approval; the
Rust collection branch remains experimental and unselected. No upstream PR was
opened.
