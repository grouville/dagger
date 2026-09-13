# Ordinary CLI-managed engine startup cohort

Separate from the completed manually provisioned readiness cohort. Same frozen
CLI source/binaries, same validated engine image, same full Rust check workload.

First CLI invokes the normal image+docker driver with a fresh unique container,
volume and XDG state. Engine image is preinstalled and verified before timing;
engine creation/readiness are inside the CLI timer. No manual engine docker run, port
lookup or engine inspection is inserted before that CLI. No artificial delay.
The two first-use timing fields now describe the same interval, not additive
provisioning/check costs.

Warm commands retain image+docker, including ordinary container lookup/start.
Do not compare absolute times against prior container:// cohorts as a code delta.
Only the paired A/B comparison isolates CLI changes here.

Normal image-driver debug listener is loopback-only and the engine has no wget.
A prebuilt static standard-library-only debug helper is copied into the owned
engine AFTER the first CLI exits, solely for post-timer profile/cache retrieval.
No measured image modification, runtime package installation, listener, result
prewarming or Cargo work is performed by the helper. Helper/source hashes are
frozen. It remains present across restart in this disposable engine filesystem.

Old-engine GC is disabled to preserve unrelated user/build engines. All new names
are proven absent before startup. Cleanup revalidates exact image/name/mount/ID;
an inspection failure cannot be accepted as absence. Partial volume-only creation
is retained/reported, not deleted without container identity proof. Cleanup errors
do not suppress the primary workload failure. No broad cleanup or user-tree edit.

Read-only review found no timer/driver blocker; its missing-volume guard and
failure-path cleanup concerns were addressed before freezing/capture. Existing
full-image byte, actual crate execution, bstr upgrade, failure/revisit/repair,
restart, wcprof completeness and cache gates remain. A failure is retained, not
replaced with another favorable sample. Cold/default-registry variability and
preinstalled-image/containerized-native limitations remain explicit.
