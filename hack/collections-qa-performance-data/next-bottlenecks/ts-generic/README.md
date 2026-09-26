# Generic TypeScript metadata experiment

Not upstream-ready; do not apply the engine hook to ordinary users. A TypeScript input edit fails closed until regeneration, which does not preserve the development UX. See `freshness-design.md` for the automatic atomic metadata+dispatch fallback and the remaining dependency/schema/key issues.

Prepared files:

- `sdk-emitter-prototype.patch`: generator emitter, generic SDK plumbing, conservative manifest sealer, and tests. The existing analyzer model emits both the TS dispatch and literal Dang TypeDefs in one generation step. Existing `EmitEntrypoint` execution callers retain their File API; Codegen gets both files.
- `engine-guard-prototype.patch`: no Kyle/frontend name gate. Any builtin TypeScript module can opt in by generated sidecar, checked against module identity and source file Dagger digests. Missing sidecar retains ordinary runtime registration. Mismatches fail explicitly. Execution stays on the original TypeScript runtime.
- `sdk-overlay.json`, `engine-overlay.json`: isolated source overlays. Engine overlay extends the same combined stack as the measured TS-static fixture; no generic engine binary has been built.
- `entrypoint_dang_test.go`: two different analyzer-model fixtures; enum/interface/list/optional/defaults/defaultPath/address/pragma/collection metadata, deterministic output, input immutability, API edit propagation, unsupported-type rejection, unresolved runtime-default parity, and generated Dang syntax.
- `fixtures/`: human-readable TypeScript companions. They have **not** been run through the actual analyzer and are not yet integration goldens.
- `test-overlay.json`: for isolated unit validation, replaces the existing templates `functions_test.go`, whose package init otherwise opens a Dagger connection. No engine is needed for the new tests. This replacement is a test harness only and is not part of the patch.

Unit command, from `/home/dagger/dag`:

```sh
CGO_ENABLED=0 go test \
  -modfile=/tmp/collections-perf/post-rebase-io/build.mod \
  -overlay=/tmp/collections-perf/sdk-edit-audit/ts-generic/test-overlay.json \
  ./cmd/codegen/generator/typescript/templates \
  -run '^TestDangStaticMetadata' -count=1 -v
```

Compile the generator with its SDK overlay and compile the SDK runtime in its own Go module separately. Four focused tests (including two fixture subtests) PASS in 0.021 s; the generator and SDK runtime both compile. See `unit.log`, `generator-compile.log`, and `runtime-compile.log`. All benchmarked numbers refer to `../ts-static`, not this unmeasured generalization.

Important prototype limitations:

- New types-only Dang entrypoint raises if called; original generated TS runtime handles actual calls. The shared SDK entrypoint should own the final call adapter.
- Missing automatic regeneration on source/schema changes; sidecar hashes are not a replacement for an authoritative analyzer.
- Whole-tree sealing currently precedes core config/VCS rewriting and can falsely invalidate after generation.
- The input guard uses `File.digest(excludeMetadata: true)` for file contents rather than reading and hashing multi-megabyte bindings over SDK RPC. It still performs per-file checks; there is no measured claim for this change.
- Manifest lacks a current dependency introspection identity. Production must include the exact dependency schema and SDK version/authority, then pair prepared metadata with prepared dispatch.
