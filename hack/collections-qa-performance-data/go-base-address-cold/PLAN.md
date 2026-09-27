# Four fresh-volume Go base Address observations

This is a prepared experiment, not a measured result. Run only after the parent
reviews the frozen driver and grants the exclusive runtime slot.

The schedule is control, candidate, candidate, control. Each of the four calls
gets its own newly created, never-started Dagger volume. Its first Dagger command
is `check -l --all`; there are no primers or hidden Dagger calls. Every command
must return the same ordered 14 checks. All four containers are provisioned while
stopped before any sample, and only one is started at a time.

All arms use engine `38711bd2…`, CLI `d6858098…`, the same existing engine image
and SDK blobs, ordinary image init, and the same copied greetings workspace path.
The local `.dagger/perf-go` directory contains only the original/candidate Dang
source and the same pinned remote gomod dependency manifest. It adds no Go
module. Control uses the original Go source and `base`; candidate uses the
reviewed optional `baseAddress` source/config. The original lockfile is restored
before each sample; normal resolver changes are recorded separately.

The CLI interval is process creation through blocking exit. Container/volume
provisioning and engine startup through debug readiness are reported separately.
Disk, engine CPU, host pressure and dirty/writeback counters bracket each CLI.
The engine write limit covers sampled lifetime writes before each final stop;
it is not a hard disk quota and excludes final stop writeback and provisioning.
The limits are four CLI attempts, 300 seconds per command, 8 GiB cumulative
sampled engine writes, and a 16 GiB free-space floor. A failed guard or output
check aborts the series without retry.

“Cold” here means an empty Dagger volume. Host pages, Docker image layers,
packaged SDK blobs and external registry/Git/CDN caches remain available. There
is no preparatory build or image pull. Fetches and compilation performed by the
first Dagger command remain inside its measured wall time. The
ABBA block has only two observations per arm and does not establish a stable
cold distribution. Both arms inherit the same experimental SDK stack; its
existing benefits cannot be credited to the new module option. No profile is
included, so elapsed time and CPU/I/O changes alone cannot prove how much time
was spent compiling the backend. Any additional phase diagnostics require a
separate explicit budget and approval.

The default cleanup stops and removes only this run's four exact immutable
container IDs, checked against the unique owner label and volume attachment.
It deliberately retains the four new volumes for inspection after success or
failure. A separate `--cleanup-volumes` operation removes only the recorded
names after checking the owner label, original creation timestamp, absence of
containers, and saved fixture restoration. Existing retained volumes and the
original benchmark engine are never referenced or modified by this driver.
All raw CLI output remains private. Only numeric evidence and source hashes
are candidates for a public archive.
