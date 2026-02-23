# Git Observability (eBPF + Dagger Cache View)

This folder gives you two layers of visibility for Git performance:

1. system-level (eBPF): process/network behavior of `git` subprocesses
2. Dagger-level (CLI `-vv` logs): cache hits/misses for Git DAG calls

Use both together to answer:
- "Did we skip `ls-remote`?"
- "Did Git DAG calls hit cache?"
- "Where is wall time spent: connect, fetch, or Dagger orchestration?"

## Files

- `git_engine.bt`: bpftrace program for git subprocess lifecycle/connect metrics
- `git_all.bt`: bpftrace program for all git subprocesses on host (no engine tree filter)
- `run-git-ebpf.sh`: helper that targets the running Dagger engine container
- `run-git-ebpf-desktop.sh`: helper for Docker Desktop / WSL2 kernel context
- `compare-main-vs-current.sh`: one-command main-vs-current perf comparison
- `summarize-git-ebpf.sh`: aggregates `git_exit` lines from eBPF output
- `summarize-git-dag.sh`: parses `dagger -vv --progress=plain` logs for Git DAG cache stats
- `summarize-git-vv.sh`: parses `-vv` logs for both DAG Git cache stats and low-level `git ...` command timing

## Prerequisites

Host requirements:
- Linux kernel with eBPF support
- root access for bpftrace
- Docker installed
- `bpftrace` installed

Ubuntu example:

```bash
sudo apt-get update
sudo apt-get install -y bpftrace
```

## Quick Start

In terminal A, start eBPF tracing:

```bash
sudo sh -c './hack/ebpf/run-git-ebpf.sh | tee /tmp/git-ebpf.log'
```

For Docker Desktop / WSL2, use:

```bash
sudo sh -c './hack/ebpf/run-git-ebpf-desktop.sh dagger-engine-v0.19.11 --all-git | tee /tmp/git-ebpf.log'
```

In terminal B, run your Dagger workload with verbose logs:

```bash
dagger -vv --progress=plain call engine-dev test \
  --pkg ./core/integration \
  --run '^TestGit/TestKeepGitDir$' \
  --test-verbose 2>&1 | tee /tmp/dagger-vv.log
```

Then summarize Git DAG cache behavior:

```bash
./hack/ebpf/summarize-git-dag.sh /tmp/dagger-vv.log EngineDev.test
```

Or get both DAG-level and low-level git command timing:

```bash
./hack/ebpf/summarize-git-vv.sh /tmp/dagger-vv.log EngineDev.test
```

And summarize eBPF git process/network totals:

```bash
./hack/ebpf/summarize-git-ebpf.sh /tmp/git-ebpf.log
```

## Main vs Current Comparison

Run the same workload on `main` and on your current checkout, with the same eBPF + `-vv` summary pipeline:

```bash
./hack/ebpf/compare-main-vs-current.sh \
  --engine dagger-engine-v0.19.11 \
  --run '^TestGit/(TestGitTreeCacheAcrossProtocols|TestGitTreeDigestTracksContent|TestGitFunctionCacheInvalidation|TestGitRefFunctionCacheInvalidation)$'
```

If you already run as root (or cannot use `sudo` in your environment), pass:

```bash
./hack/ebpf/compare-main-vs-current.sh --engine dagger-engine-v0.19.11 --sudo-cmd ''
```

If you only want `-vv` comparison without eBPF:

```bash
./hack/ebpf/compare-main-vs-current.sh --engine dagger-engine-v0.19.11 --no-ebpf
```

Custom workload command:

```bash
./hack/ebpf/compare-main-vs-current.sh --engine dagger-engine-v0.19.11 -- \
  dagger -vv call engine-dev test --run '^TestModule/TestContextGitRemote$' --test-verbose
```

## What You Get

From eBPF:
- per-`git` process lifetime (`git_exec`/`git_exit`)
- connect syscall count + total connect time per git process
- rough socket byte totals (`sendto`/`recvfrom` paths)
- histogram of git process duration

From `summarize-git-dag.sh`:
- Git DAG cache hit ratio (`CACHED` vs `DONE`)
- total/avg duration per Git DAG op:
  - `git`
  - `GitRepository.*`
  - `GitRef.*`
- optional share of parent operation time (e.g. `EngineDev.test`)

From `summarize-git-vv.sh` (adds command-level view):
- per-subcommand totals (`ls-remote`, `fetch`, `remote-metadata`, `rev-parse`, ...)
- status split per subcommand (`CACHED`/`DONE`/`ERROR`)
- top slow full git command lines

## Notes

- Existing in-engine eBPF tracers (`engine/ebpf/filetracer`, `engine/ebpf/ovltracer`) focus on overlay/file behavior, not Git subprocess latency.
- For "perfect" end-to-end correlation per API call, keep `dagger -vv` logs and eBPF output with timestamps from the same run.
