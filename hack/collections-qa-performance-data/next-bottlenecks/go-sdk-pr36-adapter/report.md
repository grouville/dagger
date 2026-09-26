# Adapt the existing Go manifest-v2 prototype to the current engine

Status: isolated source patch prepared; **no compilation, tests, SDK generation,
engine calls or performance measurements have run for this adapter**. Formatting
and textual patch application were checked. The full checkout is not copied
here; `original/` contains the exact selected upstream source files, while
`candidate/` contains their proposed replacements.

This reuses [Solomon Hykes’s Go SDK PR #36](https://github.com/dagger/go-sdk/pull/36),
head `4dfd447d58344835a0d4692ec0c8e5683c18bd6f` on `manifest-v2`. It does not
introduce a second metadata emitter or claim authorship of the prototype.
`provenance.json` pins the source; `changed-files.json` hashes the changed files;
`current-engine-json-contract.patch` applies on that exact upstream head.

## What is promising

The PR uses the existing Go analyzer, codecs, pragma handling, source maps and
static dispatcher. Its emitted Dang entrypoint returns TypeDef declarations
from `types(workspace)` without invoking a Go runtime or building a Go binary.
The real function implementation remains in Go; `call` builds the dispatcher
lazily with ordinary content identities and compiler/dependency cache volumes.
That removes registration work instead of caching the output of an unnecessary
registration process.

The current full-listing profile still contains four Go registration runtime
processes, plus the backend constructor and goTestBase. Some registration
processes overlap. Their sum is **not** a promised wall-time gain, and converting
only local backend/greetings modules may not remove all four. The profile has
call digests but does not identify every SDK/bootstrap module by source name.
SDK self-metadata and transitive legacy modules must be matched explicitly.

The public PR description refers to a previously incomplete engine loader. The
current branch already has `core/sdk/dang/v2/entrypoint.go` and the manifest-v2
loader. Compatibility must be checked against this source, not inferred from
the older description.

## Minimal compatibility changes

1. The generated Dang `call` contract changes `fnArgs` from the former list of
   FunctionCallArgValue to `JSON!`. The engine's `FunctionArgsJSON` supplies a
   JSON object keyed by original argument names with raw JSON values.
2. Dang JSON scalars are string-backed. Re-encoding one with JSON.encode quotes
   the JSON document. The transport now JSON-encodes only receiverType/fnName,
   forwards raw receiver/argument JSON into the envelope, and returns stdout
   as a JSON scalar. This also fixes the existing receiver/result boundary,
   rather than adding an argument-map change that would double-encode values.
   The engine validates input JSON and the dispatcher validates the envelope;
   identifier strings still pass through the JSON encoder.
3. The existing dispatcher receives `map[string]json.RawMessage`, then converts
   values to its existing `map[string][]byte` DaggerDispatch API. The developer
   CLI now hands over its already-built argument map; the old map→sorted list→map
   round trip is removed. Defaults, required checks and JSON/null handling stay
   in the existing developer parser.
4. The PR's contract checker and six direct engine-call e2e payloads use the
   current shape. Existing e2e assertions retain strings, lists, null, nested
   Dagger calls and core object IDs.

These changes do not alter the analyzer, generated schema semantics, runtime
build strategy, dependencies, public module methods or cache policy renderer.

## Prepared regression coverage

`TestCheckRejectsLegacyArgumentList` ensures the old list-shaped signature fails
the actual Dang contract checker. The existing positive contract test uses the
new JSON signature.

`TestGeneratedDispatchJSONMap` emits the real dispatcher into a temporary Go
module with a small recording implementation and runs its engine-call path.
It preserves receiver state, nested objects/arrays, absent versus null values,
false, escaped strings, and an integer above 2^53 without a float conversion.
It also rejects the old array payload and trailing JSON and exercises the
existing developer CLI defaults/required/null behavior. The generated temporary
module uses the standard library only, with GOPROXY disabled and local toolchain.
This is prepared test code, **not a passing-test claim**.

After restoring the full exact upstream checkout and applying the patch, run:

```
cd helpers/codegen
go test -count=1 ./generator/gogenerator/templates -run 'Test(DeveloperArgEncoding|EntrypointContractSurface|GeneratedDispatchJSONMap)$'
cd ../entrypoint-contract
go test -count=1 . -run '^TestCheck'
```

The helper contract is pinned to Dang v2.1.3 upstream; the target engine uses
v2.1.4 with the existing isolated syntax changes. Both parsing/typechecking
boundaries must be validated. A generated entrypoint must then run through the
current engine to prove the **Dang envelope as well as the Go dispatcher**
round-trips raw JSON, because pure transport tests alone do not prove this.
No new engine/Cloud commands should run until root grants the measurement slot
and the pending telemetry approval is resolved.

## Migration and correctness before timing

- Use a full checkout of the pinned PR with this small adapter. Existing
  `Mod.generate` is the normal authoritative path: stage dependency generation,
  obtain live introspection, call the existing helper, and check the contract.
  The separate `generateV2` helper's bundled beta.11 core-only schema is a
  bootstrap convenience, not a substitute for current dependency bindings.
- The PR requires an importable package. Backend/greetings are still package
  main. Renaming source before resolving the old runtime may break the schema
  bootstrap. Capture the compatible live schema before that rename or follow
  the PR's migration entrypoint, then let the **same existing helper** generate
  code. Do not hand-edit registration metadata or bypass the TS freshness guard.
- The old manifest has disableDefaultFunctionCaching=true. The new v2 manifest
  does not carry that blanket option. Preserve legacy method/constructor policy
  explicitly during migration; changing caching defaults would confound both
  semantics and timing. The separate constructor-cache experiment did not prove
  a total-time gain and should not be bundled into this comparison.
- Preserve source Directory/defaultPath/ignores, method flags, settings,
  dependency bindings, IDs and source links. Compare old/new public type graphs.
  Verify changed source is visible across new clients/sessions and after real
  mutation, while session-cached image resolution remains session-scoped.
- Check nested module cwd and go.mod root mounting. Current engine workspace
  scoping distinguishes local module sources from git/directory sources; the
  PR's goRoot/findUp/mount logic must fit that contract for each source kind.
- Run ordinary `check -l --all`, filtered collection selection, actual selected
  test check, API sentinel failure, restored six-test check, constructor/module
  calls and generation. Include independent small Go/TS/Dang marker fixtures;
  those earlier prepared fixtures have not yet run.
- Once correct, use matched warm and edit pairs with profiles taken separately.
  Report CLI→selected Check producer, CLI→Check.sync, actual test-process start,
  execution and exit tail separately. Count which registration processes were
  removed and identify any remaining SDK bootstrap work. Do not promise 400 ms
  or four removed processes solely from the historical profile sum.
