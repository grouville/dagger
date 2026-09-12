# Experiment checkpoint: repeated native Dang source discovery

This branch records a measured next optimization target, not a speedup or a
shipping cache change. It is based on main6bf59d50654ce9244ebeee1cc090b7dce3fe3083.
The diagnostic engine was built from reviewed stack
db9d005c715ac9d146780d783faf7f7b55d23e5e plus the inert
[diagnostic.patch](diagnostic.patch). The patch targets that stack; this evidence
branch does not reproduce all its prerequisites. No private wcprof code, PR,
maintainer approval, global AST cache or resident CLI is included.

## Why this is next

After the separately published client HTTP readiness improvement, wcprof still
attributed roughly 50–60 ms self time each to native Dang module loading and
Rust.check. Native Dang already runs in the engine, not in a module container.
Add passthrough spans to split schema selection/open/decoding, source mounting,
declared-type discovery, source evaluation, function evaluation, telemetry flush
and nested listener/shutdown. Preserve Dagger's user-facing span attribution.
Nothing changes cache identities, return values, source inputs or session reuse.

One fresh instrumented ripgrep workflow completed with the same pinned module,
toolchain, ordinary CLI, real edits and single bstr 1.12→1.13 upgrade. Six wcprof
captures passed complete-span, actual-execution, package, image-byte and restart
gates; three cache snapshots and six timed warm-rebuild parity audits passed.
All six replays rounded to −0.0% drift. These are diagnostic measurements, not
before/after evidence: the engine adds spans and does not include the separate
verified-image-stream experiment. Full process times remain in the report.

Exact-hit diagnostic, milliseconds (inclusive walls, not CPU or additive savings):

| Phase | Module declaration | Function invocation |
|---|---:|---:|
| Schema selection | 7.618 | 8.377 |
| Schema decoding | 6.606 | 8.575 |
| Discover own type names | 13.241 | 12.982 |
| Parse/infer/evaluate source | 36.646 | 14.825 |
| Nested listener | 0.054 | 0.068 |
| Nested shutdown | 0.043 | 0.125 |

Function-side discovery is also 13.570 ms on library repair, 12.696 ms on the
post-recovery application diagnostic, and 12.661 ms on the actual external
upgrade. Declaration source evaluation varies: 14.498–15.486 ms on those three
warm diagnostics versus 36.646 ms in the exact sample. Do not project the exact
sample's larger value as a stable gain. Function evaluation includes GraphQL
work and waits; its duration is not a CPU cost. Listener cleanup is not the
large bottleneck in these captures. [phase-report.json](phase-report.json)
retains every phase, ancestor, invocation and timing rather than only this row.

## Safe implementation boundary

`ensureModuleSelfTypes` parses all .dang files to collect public names, then
`DeclareDir`/`RunDir` parse those same files again. Both steps currently run in
each module declaration/function invocation. Explore parsing once per evaluation
phase and sharing the parsed source with name discovery and normal evaluation,
using a suitable Dang library API. Preserve deterministic multi-file ordering,
file-local imports, error recovery, source positions, all public type kinds,
normal inference/evaluation and per-invocation client/service ownership.

Do **not** just skip discovery when IncludeSelfInDeps is true. That flag attaches
the exported module definitions, but discovery also finds public scalar names;
`initDangModule` omits scalar module definitions and represents their values as
strings. Consequently, the flag does not prove every synthesized Dagger.<Name>
is present. Do not silently remove that name-resolution behavior to gain 13 ms.
Existing main/secondary self-call, enum/interface/scalar and versioned-syntax
tests are useful gates; qualified scalar-name coverage is additionally needed.
The source-parsing/evaluation split is not implemented or measured yet.

## Reproduction and provenance

Retained owner `/tmp/dagger-dang-phase-profile.Wxf82Xws`;
workflow `/tmp/dagger-rust-loop-5j_rd9hg`.

```sh
# Single-use host-specific scripts: create fresh owned paths for a rerun.
python3 /tmp/dagger-dang-phase-profile.Wxf82Xws/build.py --plan
python3 /tmp/dagger-dang-phase-profile.Wxf82Xws/build.py --execute
python3 /tmp/dagger-dang-phase-profile.Wxf82Xws/profile.py --execute
python3 /tmp/dagger-dang-phase-profile.Wxf82Xws/analyze.py
```

Build uses supported `dagger --x-release ... api call dev deploy`, an owned
never-started placeholder and a new image/container/state. Existing engines and
source are preserved. Focused `TestNestedClientServer` tests passed with local
loopback access; the first sandbox-only attempt failed to create sockets and is
retained, not counted as a product failure. The real workflow exercises the
instrumented v2 runtime. The adapter cleans only its own temporary runtime state;
its receiver is stopped and cleanup was independently verified.

| Pin | SHA256 / identity |
|---|---|
| Diagnostic engine | 45ba20522576cdce8feb36a7578fcc6118468634d6b70f5babcfdf51569b7cd8 |
| CLI with readiness change | 98fc6ea8e60fc574117300dce9334d008ee4317ee35bce5a8eebe03455110d3a |
| Unchanged workload adapter | 629c75d15da8d187960ea19e2d79f31e3238079b14a17f4a889e3ce7a3e17c54 |
| Build controller | aa11b8fce01ef6680731671a27648189d98387b82241e89c8834f0ff47bc10d6 |
| Capture controller | 0f9f0f3e0aac971edaa98ce4f3ea0819ba05cab38ecc2aced86e41eebdc306ab |
| Build manifest | 46b97cb6e74f9aebbc58badcee2e93f885cd365e31e34806719a52ab11419a5d |
| Raw telemetry, 7,526,385 bytes | aca373f8a0403cc410386cbc88b95e3bdf5a01776f4624bb2f0f9c7ee421d336 |
| Phase report | 727bb7d0cd814b40cda8ebd60654ee9b73f370b524974ac44bfd2f7dba227a53 |

No new native parity, full onboarding, artifact, macOS or remote performance
claim. Ordinary timed app edits still rebuild only ripgrep; library edits rebuild
grep-printer/grep/ripgrep. The separate application diagnostic follows failed
library revisit and a cached repair and rebuilds all three; do not confuse it
with the ordinary timed edit. No workload history or gate was weakened.
