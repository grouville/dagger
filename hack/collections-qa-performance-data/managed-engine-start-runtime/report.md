# Managed Docker start elision: small fixed-work reduction

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
