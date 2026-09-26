# Repeated service image resolution: existing lock behavior first

The completed vertical v2 service profile records Container.from at roughly
892 ms and an enclosing Dang invocation at roughly 951 ms. These overlap;
they are not additive CPU costs. The fixture uses `busybox:1.37` and its Git
workspace has no dagger.lock after repeated up/readiness/SIGINT cycles.
This makes image resolution a concrete diagnostic target, not yet proof that
all 892 ms is registry/network time.

OCI pins are **automatic** in the current API; no missing opt-in is apparent.
`core/schema/lockfile.go` enables lookup locking from v1.0.0-beta.10. The fixture
declares v1.0.0. A tag-only Container.from is deliberately scoped to the current
session, while a canonical digest can reuse ordinary immutable results.
Inside from, a valid workspace oci-sha entry bypasses ResolveImageConfig,
attaches the digest to the reference and selects the digest-addressed from.
Absent a pin, the resolver runs and the result should be recorded for shutdown
flush if a writable workspace lock is bound.

`CurrentWorkspaceLock(ctx, true)` consults the executable client's workspace.
That binding requires both HostPath and LockFile. Nested clients inherit their
nearest parent workspace. The session records the workspace owner's lock delta
and flushes it through the owner's host access during shutdown. The current
source therefore leaves three main explanations to distinguish: the lookup's
API/scope bypasses locking, the nested runtime lacks the relevant writable
workspace binding, or the newly recorded lookup does not persist at service
cancellation. The existing profile alone cannot pick one.

`service-lock-source-provenance.json` hashes eight relevant function bodies.
They match main base d8f1f0d6, retained branch c12a34663b and current shared
source. The retained TS-static engine overlay does not override these files.
This is source provenance, not a live observation of the chosen branch.

The completed `service-lock.py` used the v3 fixture and production CLI
under the same audited local-only environment. It runs one **finite** root-core
`container from --address busybox:1.37 image-ref`, records before/after lock
entries, then performs three ordinary up/readiness/cleanup repetitions and
one separate profiled up. No manual digest pin, source edit or configuration
change is performed. The original input bytes and port are retained.

If the finite root lookup creates the normal pin and service resolution becomes
cheap, investigate why the first up did not persist it. If the pin exists but
nested up still resolves, inspect the nested executable client workspace/view.
If root itself cannot write the pin, start at the view/host lock binding and
owner flush. A later finite module `web` call can distinguish nested binding
from SIGINT-specific persistence; it is deliberately not bundled into the first
five-command diagnostic.

`dagger workspace update --no-generate` refreshes existing runtime lock entries;
it does not discover every image inside every user function when no entry
exists. It is the normal refresh UX once the entry exists, not a replacement
for diagnosing the missing automatic write.

The diagnostic remains a retained-engine service test. A pin can eliminate
repeated mutable-tag lookup without changing the module's image expression,
but initial digest/blob download, materialization and service/network setup
remain real work. The root cause of the missing automatic write remains unresolved.

## Completed lock-read diagnostic

`service-lock-v3/results.json` records the finite root call creating the normal
357-byte root dagger.lock. It contains an `oci-sha` entry for
`docker.io/library/busybox:1.37`, digest
`sha256:bdf57e528e45e4433820e045b29b4597825a1c9e38353532d90a01445013f82e`.
No module source, config, input, image expression, or cache policy changed.
Every subsequent up read kept that same lock file unchanged.

The three unprofiled HTTP readiness samples were 468.795, 430.116 and
455.214 ms, median 455.214 ms. Complete foreground-command lifetimes were
539.660, 545.336 and 578.674 ms; those include the intentional SIGINT and
cleanup. The separate profiled invocation reached readiness at 410.297 ms
and exited at 512.464 ms. The profiled sample is not mixed into the three
unprofiled measurements. This supports sub-500 ms service readiness in this
small retained-engine/local-only fixture, not sub-500 ms command exit or cold
startup across arbitrary stacks.

| Separate diagnostic profile | Before ordinary pin | After ordinary pin |
| --- | ---: | ---: |
| Container.from executed call | 746.395 ms | 1.084 ms |
| Enclosing Dang invocation | 807.513 ms | 31.628 ms |
| Network setup | 69.111 ms | 42.697 ms |

The first two rows overlap and must not be summed. Both profiles have zero
dropped events. The source path and observed from duration show that normal
workspace pin reuse removes the large repeated image-resolution cost. They
do not explain why the original repeated up invocations failed to persist
their own pin.

## Prepared write-lifecycle discriminator

`service-lock-write.py` uses separate new Git roots, identical module bytes,
unchanged BusyBox tag, input and port. It adds a pure public image method for
a finite native lookup, then compares finite native calls with immediate and
delayed service cancellation. It records lock files before invocation, at
HTTP readiness, before cancellation and after exit. All of these are
profiled behavioral diagnostics, not a new performance series. The root owns
execution; consult each trial's frozen driver and declared command count.

The source already records SetLookup before Container.from returns, and the
main shutdown path calls flushWorkspaceLocks under context.WithoutCancel
before attachables close. Thus fast cancellation alone is not yet an
explanation. If finite native image lookup also fails to persist while root
core succeeds, inspect nested writable binding and dirty-lock ownership. If
finite native succeeds while up fails, additionally compare a finite call to
the exact web producer (`api call web hostname`) to separate artifact/command
binding from cancellation. If only delayed cancellation succeeds, inspect
the specific state publication/cleanup ordering; a sleep is not the fix.
