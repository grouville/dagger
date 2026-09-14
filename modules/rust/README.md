# Rust module integration candidate

Cargo-compatible checks and generated build artifacts for an existing Cargo
workspace. This is an integration prototype, not a completed official module
or a claim to beat native Cargo.

To try this checkout's module, add it to a disposable Cargo project's
`dagger.toml`, replacing the path below with this checkout's absolute path:

```toml
[modules.rust]
source = "/path/to/dagger/modules/rust"

[modules.rust.settings]
locked = true
cacheKey = "my-project-rust"
```

With a compatible development engine and a Cargo.lock already present:

```sh
dagger check rust:check
dagger check rust:fmt rust:clippy rust:test
dagger generate -y
dagger check
```

Default `dagger check` includes generator drift checks. After source edits, it
can correctly report that generated artifacts are stale; `dagger generate -y`
applies the generated Changeset. The module owns `target/dagger`, not other
target contents. Unlocked generation also publishes Cargo's actual Cargo.lock.

Project-selected toolchains, Cargo profiles, explicit targets, features, and
lint policy are retained. Source reconciliation and Cargo's intermediate cache
are locked mutable cache volumes; final artifacts are immutable Dagger results.
No listener, watch process or separate build language is required.

## Current limitations

- The toolchain image and pinned source-sync packages support only the recorded
  Linux/amd64 Debian image. Artifacts are Linux/GNU outputs, not native macOS
  outputs. Other platforms and remote-engine performance are not validated.
- The prototype requires stable Cargo >=1.91 for build.build-dir. It does not
  silently upgrade an older project toolchain.
- The module excludes `.git`, `target`, `dagger.toml`, and `dagger.lock` from
  Cargo source. Cargo.lock, .cargo/config.toml, build scripts and sources remain
  inputs. Unusual projects reading the excluded paths are outside this prototype.
- Symlink final artifacts and workspaces with no selected final artifacts are
  rejected. Ordinary Cargo output is not the same as a universal artifact model.
- Full artifact validation used the separately recorded singleton Changeset
  metadata-preservation and GC-reserve patches. This module branch does not
  silently include those engine changes. On an unpatched engine, unchanged
  parent-directory modes / empty directories can still expose the known merge
  bug; do not present that configuration as fully validated generation. Exact
  common source/binary hashes are in the benchmark's
  [engine provenance](../../hack/bench-rust-contextual-checks/engine-provenance.json).
- First use is still slow. No faster-than-Cargo, complete-installation or
  all-workflow performance claim is established.

The check entrypoints use contextual Directory inputs so unchanged content can
reuse whole function results across ordinary CLI sessions. The generator keeps
its Workspace input to observe current host artifacts independently.

See [the performance report](../../hack/bench-rust-contextual-checks/RESULTS.md)
for exact comparison scope and retained regressions. The intended final product
supports more than this prototype.
