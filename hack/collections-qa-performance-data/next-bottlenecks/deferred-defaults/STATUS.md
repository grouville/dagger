# Typed deferred configured Container default — isolated prototype

Shared source is unchanged. Core/schema compilation passed with the final
conservative fallback and preflight code. All seven focused core tests now pass
(0.068 s, unit-final.log). The earlier full scoped run also passed (0.077 s core,
0.032 s schema). A new negative test initially panicked because its fixture used
AnyID.ToLiteral on a handle-form ID; both fixtures now pass encoded IDs. That
failed log remains in unit-final-before-fixture-fix.log. There is no engine
binary or end-to-end timing yet.

The planner intercepts a configured Container default, leaving direct public
Address.container behavior unchanged. DAG addresses are resolved/type-checked
immediately. Only direct module Container functions are supported; deeper paths,
collections, custom TTLs and live Workspace function arguments retain eager
evaluation. The latter could perform new host reads at force time, so it needs a
separate semantic proof before supporting it. There is no user config or
fixture-specific gate in this mechanism.

The private canonical query returns a real Container using LazyContainerParts.
Its metadata demand invokes the frozen module constructor/function. Filesystem,
exec metadata and mounts delegate independently. Passing the ID to an SDK uses
its normal core-object input contract and does not execute the producer. The
resolved parent receives an explicit dependency on the published shell.

Arguments are prepared through ModuleFunction.DynamicInputsForCall before either
module body runs. Primitive defaults and object references are frozen; JSON uses
reference slots, not embedded engine IDs or host-path cache keys. Contextual
Directory inputs already materialize a snapshot and receive a content digest in
ModuleSource.LoadContextDir. File loading can remain lazy. Rather than force an arbitrary filesystem recipe
while planning, the prototype falls back eagerly if any File/Directory argument
lacks content identity. This preserves current execution/error behavior for the
unsupported case and avoids extra work or invented file equivalence. The
Directory defaultPath case remains supported. A metadata-only preflight checks
both constructor and leaf arguments before resolving any contextual inputs. It
falls back for configured object defaults, File defaultPath and Workspace
arguments, so it cannot run a Never-cache object default during preparation and
then run it again after an eager fallback. Optional unbound object arguments
remain unset. The preflight and negative no-evaluation tests passed in the final
focused core rerun.

Live-workspace or explicitly session/never-cache plans carry the creating session
and the existing named PerSessionInput. They reject a force in another session
before looking up workspace/client/module state, and do not persist. Same-session
nested SDK clients can receive the value normally. Ordinary engine-owned value
workspace plans can persist; module/workspace/input/parent result references use
the existing remapping API, including a declared reference visitor. The pending
shell preserves its published owner after restore. It never claims the scratch
Container.From identity optimization. No callback captures an old context.

Local tests cover:

- Lossless integer/list/null serialization and explicit reference slots.
- Invalid reference slots.
- Publishing, capturing, relocating and reopening an unused plan without invoking
  a deliberately missing producer function.
- Correct published-owner restoration, including a restore wrapper.
- Rejection of another session before any query/client/workspace lookup.
- Metadata-only rejection of unsupported defaults; unsealed filesystem inputs
  are not forced; live Workspace function inputs are not retained.

The generic fixtures have independent Go→Go, TypeScript→TypeScript and Dang→Dang
producer/consumer modules, using normal SDKs. prepare_fixtures.py writes them;
test_fixtures.py is ready but has not run. It checks:

- Ignoring a base, and expanding collections with `check -l --all`, succeeds even
  if the producer constructor or body would fail.
- A used base reports the same constructor/body error.
- A used Container reads both a copied source file and its bound HTTP service.
- An application file outside both modules changes both results on normal
  one→two→one edits, including returning the Container through its public API.
- Actual check execution, and early invalid-address/type errors.

Remaining before enablement: real module/runtime parity, same-session workspace
owner authority in nested SDK calls, app edit invalidation, service lifecycle,
pending-plan cache reload behavior under full engine ownership, and measured
preparation cost. Unsupported cases may fall back eagerly rather than weaken
those invariants. This is not yet an upstreamable enabled change.

Deferring a base saves work only for flows that never consume it. A check/up/export
that uses the base still owes its producer's work. Any listing improvement must
be reported separately from used execution and from true cold SDK initialization.

For portable review, retain prototype.patch, source-manifest.json, STATUS.md,
prepare_fixtures.py, test_fixtures.py and the unit logs. The full explicit
archive-allowlist.txt additionally retains overlay sources and local preparation
scripts; engine-overlay.json references the existing local frozen baseline and
is not a standalone portable build recipe. No schema/core code from this
prototype should be enabled on the performance branch merely because its
focused local tests compile.
