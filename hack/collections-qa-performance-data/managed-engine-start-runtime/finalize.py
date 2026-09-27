from pathlib import Path
import hashlib,json,shutil
H=Path(__file__).parent;S=Path('/tmp/collections-perf/managed-engine-start-v1');E=H/'results-v1-evidence';B=Path('/tmp/collections-perf/shared-client-transport-v1/prototype-v2/builds');R=Path('/home/dagger/dag')
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,v):p.write_text(json.dumps(v,indent=2)+'\n')
recipe=json.loads((B/'build-recipe.json').read_text());overlay=json.loads((B/'original-overlay.json').read_text());builds=json.loads((B/'build-results.json').read_text());original=next(x for x in builds if x['variant']=='original');manifest=json.loads((S/'runtime-builds.json').read_text())
assert original['sha256']==manifest['baseline']['sha256']==sha(original['path'])
source=Path(overlay['Replace'][str(R/'engine/client/drivers/container.go')]);assert sha(source)==recipe['source_guards'][str(R/'engine/client/drivers/container.go')]=='990ce4a905dbbea0e2ece84b716dc71c9ba637e68d2d5ca00a75a9a361949996'
assert 'if exists, err := d.backend.ContainerExists(ctx, containerName); err == nil && exists {\n\t\tif err := d.backend.ContainerStart(ctx, containerName); err != nil {' in source.read_text()
assert sha(B/'cli.mod')==sha(S/'builds/cli.mod')and sha(B/'cli.sum')==sha(S/'builds/cli.sum')
proof={'baseline_binary_sha256':original['sha256'],'original_build_argv':original['argv'],'original_build_recipe_sha256':sha(B/'build-recipe.json'),'original_build_results_sha256':sha(B/'build-results.json'),'original_overlay_sha256':sha(B/'original-overlay.json'),'frozen_container_source_sha256':sha(source),'frozen_container_source_matches_HEAD 0d':True,'ordinary_start_present_after_existence_probe':True,'managed_candidate_recipe_sha256':sha(S/'builds/recipe.json'),'same_cli_mod_sha256':sha(B/'cli.mod'),'same_cli_sum_sha256':sha(B/'cli.sum'),'source_order':'Connect synchronously calls startEngine. Driver.Provision calls imageDriver.create and completes inspect/start before newBuildkitClient or the first tunnel. Warm tunnel prefetch begins only after first connection bytes.','measurement_limit':'No CLI span/exec instrumentation in this ordinary matrix; exact subprocess duration and later compensating variability were not separately measured.'}
write(E/'baseline-source-proof.json',proof)
(E/'report.md').write_text('''# Managed Docker start elision: small fixed-work reduction

The prototype removes one redundant Docker start process when the selected existing engine reports the exact `running` state. All 32 local commands passed their expected outcomes. The ordinary core wall-time median was flat; this is not evidence for a general command-speed improvement.

| Warm operation | Baseline median | Candidate median | Candidate faster | Median paired delta | Median paired CLI/process-tree CPU delta |
| --- | ---: | ---: | ---: | ---: | ---: |
| Core version query |244.12ms|244.76ms|3/5|−21.40ms|−13.18ms|
| Native `generate render` |293.47ms|280.26ms|4/5|−23.77ms|−18.08ms|

The independent medians and median paired differences answer different questions and both are reported. Five alternating pairs per flow are exploratory; the mixed core signs do not support a uniform wall-time gain. Every warm generator output was already current. This measures command overhead, not faster file production or SDK code generation. Full raw values and all ten paired differences remain in the numeric files.

Two stopped-engine controls were timed through the CLI itself, without prestarting it: baseline 3566.98 ms and candidate 3579.24 ms. Both returned the exact expected engine version. These are single resume/correctness controls, not a cold-start performance comparison. Native sentinel checks failed on the expected marker and passed after restoration in both arms. Workspace listing order also matched.

The original CLI is exactly the retained `d6858098…` binary. Its recorded build command uses the original overlay whose frozen `container.go` SHA990ce4… contains the unconditional ContainerStart call immediately after the successful ContainerExists probe. That frozen source equals unmodified HEAD 0d. The candidate `a52d4604…` uses identical dependency files and changes only the three driver implementation files. Both arms use `image+docker` and the same owned container/engine; `cleanup=false` avoids sweeping unrelated engines in both arms. Unit tests separately retain and exercise the cleanup policy. The temporary local image tag referenced the existing pinned image and was removed without deleting the original tag or image.

Source order makes this work synchronous: driver provisioning performs inspect/start before the BuildKit client, first tunnel, or speculative warm tunnels exist. There is no source-supported explanation that the removed start is overlapped with those later connection steps. No CLI span instrumentation ran in this matrix, so it cannot isolate exact subprocess cost or explain each later timing fluctuation. Background/runtime variability remains part of full CLI wall time.

The final implementation queries `.State.Status`, not `.State.Running`: paused and restarting containers can have the latter boolean set, while the old start operation can produce a meaningful error. Only exact `running` skips start. Unknown state, stopped/paused/restarting states, non-Docker backends, missing containers, canceled inspection, start failure and the existing creation-race path retain the previous behavior. The boolean-field draft remains unvalidated and is not proposed.

State is a point-in-time observation, not an atomic liveness guarantee. An unrelated actor can stop a container after inspection. This patch does not add a retry or claim to eliminate that race; connection still reports failures. It changes no Dagger content cache, session authority, snapshot lifetime, mutable image policy, connection topology or shutdown wait.

The actual image-driver negative witness fails with the original branch and passes with the candidate. The normal and race suites each passed 44 test/subtest outcomes, including exact Docker command/response protocol and legacy-backend fallback. The complete 32-command trial restored all fixtures, preserved the original stopped engine and retained volume, and removed only its temporary container and image tag. No Cloud, fresh-volume cold, source-edit, service-up or broader workflow claim is made.
''')
shutil.copyfile(Path('/tmp/collections-perf/module-load-pipeline-runtime-v1/analyze.py'),E/'analyze.py');shutil.copyfile(H/'finalize.py',E/'finalize.py')
write(E/'archive-allowlist.json',{'scope':'Source, hashes and aggregate/numeric results only; excludes actual selectors/container IDs, raw stdout/stderr, payloads, profiles and credentials.','files':[{'source':str(p),'archive_name':'managed-engine-start-runtime/'+p.name,'sha256':sha(p)}for p in sorted(E.iterdir())if p.is_file()and p.name!='archive-allowlist.json']})
sourcefiles=['container.go','docker.go','container_state.go','container_state_test.go'];hashes={str(R/'engine/client/drivers'/n):sha(S/n)for n in sourcefiles};write(S/'exact-source-hashes.json',hashes)
(S/'upstream-rationale.md').write_text('''# Proposed change: skip a redundant Docker start for a running engine

A normal managed-engine command inspects the selected existing container and then invokes `docker start` even when it is running. Request the state in that existing inspect and omit start only for the exact `running` status. Keep the optional capability internal to the Docker backend; all other backends and all unknown/non-running statuses use their previous start behavior.

Use `.State.Status`, not `.State.Running`. A paused or restarting container can retain the running boolean, while start may return an error the old path exposed. This conservative interpretation preserves those errors. Missing and canceled lookups, creation races, start failures and cleanup remain covered by the focused regression tests.

This is a point-in-time observation. It does not establish atomic liveness against concurrent external stop/restart operations, add a connection retry, or replace the backend's exec authorization. There is no Dagger cache or engine behavior change.

The original branch fails the meaningful running-engine witness; candidate normal/race suites pass44 test/subtest outcomes each. The matched 32 local-command trial shows lower paired CLI/process-tree CPU, a 13.2 ms native-generation median reduction, and flat core independent wall medians. Do not claim a universal command latency improvement. See the separate runtime report and paired values.

Apply only the four exact source files in exact-source-hashes.json. The three implementation files match the frozen built overlay; the test file matches the validated test overlay. Runtime sources have not changed since validation/build. Integration and commit remain the parent task's decision.
''')
(S/'proposed-commit-message.txt').write_text('''perf: skip redundant starts for running Docker engines

Read the container state during the existing managed-engine inspection and
skip Docker start only for the exact running status. Preserve the start path
for paused, restarting, unknown and stopped states and for other backends.

Focused negative, normal and race gates pass; a matched 32-command local trial
also verifies existing-container reuse, stopped-engine resume and actual
native check failure/restoration. Core wall medians were flat; paired CPU
cost was lower and the small native generation series improved.
''')
paths=[S/n for n in sourcefiles+['prototype.patch','production-overlay.json','test-overlay.json','baseline-overlay.json','source-provenance.json','exact-source-hashes.json','upstream-rationale.md','proposed-commit-message.txt','validation-summary.json','runtime-builds.json','validate_build.py']]+[S/'builds/recipe.json',S/'builds/build-result.json']
write(S/'archive-allowlist.json',{'scope':'Exact proposed source patch, meaningful tests, pinned recipes and sanitized gate outcomes; no binaries, raw runtime data or unrelated external dependency copies.','files':[{'source':str(p),'archive_name':'managed-engine-start-source/'+str(p.relative_to(S)),'sha256':sha(p)}for p in paths]})
print(json.dumps({'source_hashes':hashes,'source_allowlist':str(S/'archive-allowlist.json'),'runtime_allowlist':str(E/'archive-allowlist.json')},indent=2))
