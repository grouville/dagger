# Address-default and retained GoModule correctness proof

Prepared only. Python syntax has been checked without importing/executing the driver. The producer is included in the SDK agent's focused Dang parser gate. No runtime result is claimed. The corrected Address engine must pass focused tests and have a reviewed frozen build manifest before this driver can run.

`runtime.py` owns a bounded LOCAL proof of nine CLI calls. It uses the independently reviewed retained-volume lifecycle: one new labeled container, the original56f2 engine and ordinary init stay stopped and unchanged, exact existing image and pinned SDK blobs,16GiB minimum free space,8GiB CLI-bracket write ceiling, joined timeout/cancellation, and removal of the new container only. No volume deletion, image pull/build, existing credential copy or production Cloud call. Engine startup/setup are outside any performance claim; this is correctness only.

The lifecycle keeps CLI d6858098… and the frozen ec6 SDK stack. The new Address engine manifest supplies its exact SHA/VCS version/recipe, and must name ec6 ancestry. `freeze.py` verifies and copies that manifest and hashes the driver, SDK blobs manifest, original/candidate module and every fixture file. Both module variants run on the same Address-capable engine. Actual build is owned by the SDK agent and scheduled by root.

## Exact sequence and bounds

1. One `dagger api with-session --load-workspace-modules` command runs probe.py. It performs exactly10 GraphQL requests (hard cap10,300seconds total; outer CLI330seconds). It captures one Workspace ID, passes it explicitly to go.module/tests/base, retains one GoModule ID, and classifies its ordinary cache behavior.
2. Fresh CLI runs the strict synthetic Go check successfully.
3. Write only service-marker.txt to an incorrect value; a new CLI must fail with the real HTTP/body mismatch and exactly one failed check. The producer still returns a successful Container; this is not an erroring-producer cache witness.
4. Restore service content, write a real failing Go assertion after the HTTP assertion; a new CLI must report that exact test failure.
5. Restore Go source and change both marker files. A new CLI must pass the strict test. The test embeds marker.txt and requires the producer's environment to match that fresh compiled source, then requires its live HTTP service to return the same generation and marker. Nothing skips.
6–7. Normal greetings CLI control: original Go-module source in the matched local layout, exact ordered14-row `check -l --all`, then the real TestE2EUnknownLanguage HTTP check with the missing-URL skip changed to fatal.
8–9. Normal greetings CLI candidate: modified source at that same location and explicit baseAddress setting; the same listing and strict HTTP check must pass.

Every failed gate stops the sequence; there are no automatic retries/primers beyond those nine commands. Ordinary calls are bounded180–300seconds. Synthetic files and the owned greetings copy's authored files are restored in finally; the original public greetings fixture is never edited and its hashes are rechecked. Normal dagger.lock updates in the owned copy are recorded separately. Raw CLI output stays private.

## Retained-session cache contract

The producer alone is NEVER. It uses the existing recording-model spawn fixture pattern to obtain a unique handle; it never calls an LLM provider. Two direct consumptions of one Address must return distinct successful generation values. Two GoModule.base calls use exactly the same retained receiver and Workspace inputs; both returned Containers must preserve their own HTTP service. The evidence records whether the outer base call reached the producer twice. It does not assume NEVER propagates transitively through a cached DEFAULT wrapper, clear caches, alter keys or add blanket NEVER annotations to make that result pass.

The earlier source-only script wrongly treated repeated currentWorkspace calls as a fresh host snapshot. CurrentWorkspace may return the session's frozen workspace; host reads use a per-client epoch, advanced after Workspace.export. An arbitrary Python host write does not supply the normal new-CLI invalidation boundary. This corrected version performs all real file-edit gates in separate CLI sessions, and keeps retained-handle caching as a distinct observation. The original unexecuted script is preserved for provenance, not a failed engine trial.

## Fixture and authority

The synthetic proof is outside timed greetings. It contains one Go module/test and a Dang producer; pinned images are the already-used BusyBox1.37 digest bdf57e… and greetings' Go1.26-alpine digest51a7c3…. No helper Go modules are copied beneath the app. `baseAddress` is under `[modules.go.settings]` using camelCase: current settings lookup is case-insensitive, not kebab-normalizing.

Both greetings arms use only go.dang plus dagger-module.toml in `.dagger/perf-go`, with the original remote gomod dependency pinned at1784ff37…. Both arms thus share the local-source/admission difference. No normal-remote latency improvement may be inferred from this matched local-module correctness proof. The configured Address preserves its originating Workspace; it is not reconstructed from an arbitrary later String/workspace.

The previous held generic lazy-default prototype tried to preserve transparent eager-Container behavior while freezing implicit ambient inputs. This explicit new Address option exposes the force point to the module author/user and intentionally changes when target errors occur. The generic Address-ID fix is independently testable; none of this enables that older broad lazy-default mechanism.

## Default selected-check semantics

The driver intentionally keeps the default `--generated` behavior. `internal/cmd/dagger/artifact_execution.go:commandArtifacts` narrows the exact go/modules/tests/run path plus keys before `selectCommandChecks` applies filterCheckCommand. `core/schema/artifacts.go:filterArtifactCommand` filters existing entries; enabling generated checks does not append unrelated generators. Its staleness policy only applies to a selected Check whose parent is a generated Changeset. Thus each exact selected test should still produce one check, while full `check -l --all` continues to list generated-file checks without evaluating or exporting them. No timing shortcut flag is added. Unexpected authored/generated source mutations still fail the fixture guard.

Freeze inputs include the public APP inventory and every inventoried file, the ordered listing golden, original retained-engine ownership manifest, and all three imported Python helper sources. Setup and execution reject drift before any engine operation.
