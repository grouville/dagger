# Direct-write CAS with asynchronous admission

CAS-only experiment: no composefs, EROFS or Btrfs. Missing files are constructed
directly in the private result snapshot. After commit, an engine-owned task
retains the finalized inodes in the optional CAS via hardlinks. Existing cached
inodes can populate later flat result snapshots. The writable source mirror is
never hardlinked into the immutable result. There is no growing overlay chain.

This is **experimental, not an upstream-ready perf-prod patch**. The code has
focused regression tests, but sustained GC, restart/crash recovery, overlapping
imports and writable-container isolation still need broader validation.

## Published benchmark

- [Detailed results](results/DETAILS.md): engine and standalone CLI times, ranges,
  phase breakdowns, client scan and background admission tails.
- [Summary](results/RESULTS.md) and [all 234 timings](results/samples.csv).
- [Contention disclosure](results/CONTENTION.md): unrelated compilation was
  observed during round 5; the exact onset is unknown. No outliers were removed.
- [Original benchmark controller](historical/matrix_async.py),
  [capture contract](historical/ASYNC-MATRIX.md) and its helpers are preserved.

| Arm | Exact measured source |
| --- | --- |
| Main + common instrumentation and GC reserve-floor fix | `c4512cf1d1a371ca097d13a311c523638f4c7c0b` |
| Direct-write CAS + xattr opt-out, synchronous admission | `31064758056ac175f54941d6293eff1905df894a` |
| Same CAS, asynchronous admission | `79a5f0800755dfb8316dd9575cd745ad2f5075db` |

The branch also includes `5624b8c6`, bounding the view lease lifetime. It passed
focused tests, but **is not the measured candidate**. Subsequent commits package
the benchmark; they do not claim new engine performance.

Six cyclically ordered rounds, three arms, 13 flows. On Ruff, engine medians for
main / synchronous CAS / async CAS were 2229 / 2543 / 2488 ms cold and
1205 / 832 / 815 ms after a one-file edit. Cold remains slower; async alone is
not a demonstrated consistent end-to-end improvement over synchronous CAS.

"Cold" means new engine volume and CLI state, with engine images and host OS
pages already available. It excludes image builds/downloads and installation.
This is filesync only, **not Cargo or Rust-module performance**.

The reports are the original outputs. Their absolute `/tmp` references point
to retained evidence on the original host, not downloadable GitHub artifacts.
Raw native dumps and the full 1.4 MB `RESULTS.json` remain there; `samples.csv`
publishes all timings plus profile/receipt hashes, not the underlying dumps.
The archived controller is machine-bound (paths, helper hashes, build receipts).
Do not run its historical commands on another machine expecting them to work.
Use the portable runner below for a **new, separately labeled cohort**.

## Prerequisites

Linux with a local privileged Docker daemon, its containerd image store enabled
(the original machine used Docker 29), Python 3.11+, Git, Go, and a Dagger CLI
able to build this checkout. Allow enough disk for 18 independent engine volumes
plus three engine images; the runner deliberately does not prune anything.
No special filesystem is needed. The published comparison used overlayfs.

Native `wcprof-analyze` is required on PATH or by absolute path; this repository
does not distribute that executable. Use the maintained analyzer available in
your development environment. The runner records its hash and requires a
successful replay with <=2% drift. Do not substitute fabricated phase timings
if the analyzer is unavailable. Building the engines requires network access;
the timed imports use preloaded local images.

Use an otherwise idle host. Stop your own heavy builds before measuring, not
other users' containers. The harness does not change kernel limits, Docker
settings, global GC configuration or host page caches.

## 1. Fetch the implementation and exact comparison revisions

Run in a new directory; these commands do not modify an existing checkout:

```sh
git clone --branch exp/filesync-async-admission https://github.com/grouville/dagger.git dagger-cas
cd dagger-cas
git fetch origin exp/filesync-async-baseline
git worktree add --detach ../cas-main c4512cf1d1a371ca097d13a311c523638f4c7c0b
git worktree add --detach ../cas-sync 31064758056ac175f54941d6293eff1905df894a
git worktree add --detach ../cas-async 79a5f0800755dfb8316dd9575cd745ad2f5075db
git clone https://github.com/astral-sh/ruff.git ../ruff-filesync
git -C ../ruff-filesync checkout --detach c2cd236b9cc5b2149c74247e179d6567ec74066f
```

To test the latest lease fix instead of reproducing the measured code, create
the async worktree at `5624b8c6` and label that arm `async-leasefix`.

## 2. Build and load each image, outside the timed comparison

From each worktree, use the normal engine-dev module. For example:

```sh
bench_root="$(mktemp -d /tmp/filesync-cas-build.XXXXXXXX)"
for arm in main sync async; do
  (
    cd "../cas-$arm"
    dagger api call engine-dev container --platform=linux/amd64 \
      as-tarball --forced-compression=Gzip --output "$bench_root/$arm.tar"
  )
  python3 hack/bench/filesync-cas/load.py "$bench_root/$arm.tar" "localhost/filesync-cas-bench:$arm"
done
```

If your installed CLI requires selecting the development release, put its
`--x-release <compatible-release>` before `api call`. The original builds used
release `00cb7d3a0e8d1eb6ec672aa504db14e52a9d1e21`. This build step may take
minutes; none of it belongs in the filesync stopwatch. `load.py` refuses existing
tags: choose new tags on reruns rather than overwriting someone else's images.

The runner extracts the matching CLI from each image automatically. On ARM64,
build **all** images and the helper for linux/arm64; that is a new platform
measurement, not the published amd64 result.

## 3. Build the profiling helper and run

The tiny helper accesses only the engine's loopback debug endpoint; it avoids
publishing a host port or requiring curl inside the engine image.

```sh
CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build \
  -o "$bench_root/debugget" ./hack/bench/filesync-cas/debugget/main.go

python3 hack/bench/filesync-cas/run.py \
  --ruff ../ruff-filesync \
  --output "$bench_root/measurements" \
  --arm main=localhost/filesync-cas-bench:main \
  --arm sync=localhost/filesync-cas-bench:sync \
  --arm async=localhost/filesync-cas-bench:async \
  --rounds 6 \
  --analyzer "$(command -v wcprof-analyze)" \
  --debug-get "$bench_root/debugget"
```

Use `--rounds 1` for a smoke test, in a different output directory. Each run
requires a nonexistent output directory. It copies Ruff there before applying
any edit; your supplied checkout and official Rust module remain untouched.

The flows are cold, unchanged, one-file edit/repeat, directory move/repeat/restore,
128 edits + 64 additions + 64 deletions/repeat/restore, and 24 directory moves +
64 file renames + 32 additions + 32 deletions/repeat/restore. Every arm gets the
same bytes, names and mtimes. Arm order rotates between rounds.

Each command is a new CLI process. CLI wall time and native query time are
separate. Native profiles retain background admission beyond CLI exit; the
runner drains it before the next sample. Consequently this is **not** an
immediate-next-request overlap or throughput benchmark. First-round full-tree
exports validate content/types/links/names for all four changed trees; export
mode normalization is recorded separately, matching the historical limitation.

## Outputs, checks and cleanup

`measurements/RESULTS.md` contains the new summary; `samples.json` contains
every successful sample and phase duration. Per-flow directories retain stdout,
stderr, source manifests, native profiles, analyzer output, PSI pressure, async
tail and ownership records. Failure stops the run and retains partial evidence;
it never fills missing rows from the old matrix.

The portable runner is a new wrapper around the original fixture/validation
helpers, not the script that produced the published numbers. Its validation
must be reported separately; do not pool new runs with the frozen cohort.
At publication it has local helper/unit coverage, but has not completed a new
end-to-end Docker matrix. Start with the one-round smoke test before a full run.

Run the local helper tests (no engines started):

```sh
python3 -m unittest discover -s hack/bench/filesync-cas/historical -p 'test_*.py'
python3 -m unittest discover -s hack/bench/filesync-cas -p 'test_run.py'
python3 hack/bench/filesync-cas/run.py --help
```

Engines are sequential, and stopped by their recorded container IDs. Containers,
volumes, backups and results remain for inspection. Names are unique:
`dagger-filesync-share-<nonce>-r<round>-<arm>`. Inspect those exact names and IDs
in each `inputs.json`/`owner.json` before manually removing them. Never use a
global Docker prune as benchmark cleanup. If killed with SIGKILL or an early
provisioning failure, inspect the recorded engine name for a surviving container.
