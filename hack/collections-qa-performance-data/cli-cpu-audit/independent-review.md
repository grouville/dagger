# CLI CPU capture: independent source review

The prepared driver runs 11 local-only commands: three primers, seven CLI CPU/runtime-trace captures, and one separate wcprof listing capture. It selects frozen CLI `748700a2…` and engine `9912b763…`, checks expected stdout, isolates credentials/export environment with a fresh config, and restores the original stopped task engine binary. It does not claim ordinary latency. The fixed command bound and 120-second command timeout with bounded signal/kill cleanup are appropriate for this diagnostic. No runtime was executed by this reviewer.

Add process-tree CPU snapshots immediately before Popen and immediately after wait, before subsequent Docker/resource/profile calls. Those brackets must exclude the Python driver's own Docker inspection helpers; record user and system CPU separately. The exact build manifest, driver hash, fixture hashes and original engine identity should remain beside every run. A mid-run failure still needs the existing stop/restore finally block; only report completed rows as validated.

## CPU accounting boundaries

- Go pprof records samples from the Dagger process only. Docker CLI children are distinct processes and their execution does not appear as their own functions in that profile.
- CPUPROFILE starts in the root command's PersistentPreRunE (`internal/cmd/dagger/main.go:274`) and stops through Cobra OnFinalize. Go/package initialization, command-tree creation and earlier argument parsing precede it; later finalization/process exit can follow it. Their CPU is outside the sampling interval even though it belongs to Dagger itself.
- RUSAGE_CHILDREN in the Python driver counts waited child processes and their reported waited descendants. It is not Dagger-process-only CPU. A child that outlives Dagger and is reparented is not guaranteed to be included.
- Docker daemon, container-side buildctl and engine CPU are outside this host child-process accounting. Engine cgroup counters are another scope. The same command may involve all three scopes.
- Short Go CPU profiles are sampled and quantized. Profile CPU totals need not exactly equal process CPU, particularly while a Go execution trace is recorded simultaneously. Neither their difference nor a single missing sample is a precise estimate of a specific unprofiled function.

Therefore tree CPU minus sampled Dagger CPU must be labelled an unexplained accounting difference, not automatically Docker CPU or profiler overhead. Separate self/children process accounting or bounded per-subprocess counters would be needed for that attribution.

## Source-confirmed subprocess path

`GetDriver` invokes backend availability. The Docker backend executes `docker version` (`engine/client/drivers/driver.go:69`, `docker.go:24`). Container-driver provisioning itself does not inspect or start the already selected container. Each `containerConnector.dial` runs `docker exec -i <container> buildctl dial-stdio` via Docker commandconn (`container.go:278`, `docker.go:113`). Once the first connection answers, the connector proactively dials three more tunnels for later client libraries (`container.go:178–207`). Further connections dial on demand. These source paths establish possible separate host processes; exact counts, use and CPU still need runtime evidence. The source comment's historical approximately 40 ms tunnel latency is not a measurement from this run.

Docker commandconn owns subprocess Wait/termination during connection EOF/Close. Unconsumed speculative tunnels can remain until the parent exits, so do not assume every launched process has been waited before the outer accounting snapshot. The source-only opportunity to investigate is avoiding redundant availability work or replacing repeated executable startup with a shared supported transport, while preserving runtime selection/context/error diagnostics. Do not adopt either based solely on an unexplained CPU difference.

Git metadata is mostly loaded through go-git in-process and would appear in the CLI profile when it runs after profiling starts. LoadDefaultLabels uses sync.Once, so calls from main and client connection do not imply repeated Git reads. The shell Git fetch/update-ref paths are conditional on GitHub PR environment; that environment is absent from this isolated driver. Existing old checkout-specific 220 ms claims must not be reused.

## Saved-profile analysis plan

Compare each flow's repeated CPU totals and aggregate flat/cumulative function families, keeping sampled totals visible. Use the runtime trace only to distinguish Dagger runnable/blocking intervals and observed subprocess wait boundaries; it does not profile child execution. Separately inspect the wcprof listing's operation window and count/completeness, without adding concurrent durations as wall time. Retain only function names and numeric counts/timings in shared evidence; raw CPU/trace/wcprof and stdout/stderr remain private. Treat the resulting profiles as leads for focused tests, not another ordinary latency benchmark.
