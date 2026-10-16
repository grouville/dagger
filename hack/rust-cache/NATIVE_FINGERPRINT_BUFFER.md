# Buffered native package fingerprints

The isolated buffer change is [7e5e40536](https://github.com/grouville/dagger/commit/7e5e40536c30a4b97fcb8d5fdb510c57d5ca904c), on `perf/tree-fingerprint-buffer`. It reuses one lazy 32 KiB copy buffer while reading files. Hiding `os.File.WriteTo` ensures `io.CopyBuffer` uses that buffer. The fingerprint format, metadata policy and rejection rules stay the same. This remains part of the experimental native fingerprint API, rather than an independent main fix.

Five fresh-process alternating component pairs produce identical digests in both arms:

| Workspace | Before time | Buffered time | Allocated bytes before → buffered |
| --- | ---: | ---: | ---: |
| 128 crates | 8.57 ms | 7.16 ms | 5.57 MB → 1.31 MB |
| 1026 crates | 64.15 ms | 56.32 ms | 44.56 MB → 10.19 MB |

The complete `engine/contenthash` race suite passes on the committed source.

## Complete edited commands

The command comparison evaluates shell discovery (`cd6d25e`) against the complete native fingerprint path (`e9a9981`) on the same buffered engine. Both scripts are local bindings, so this comparison avoids the old serialized-script-field difference. Source snapshot seeds and compact scalar-array restoration are enabled. Telemetry remains enabled with the same decoding/null receiver; wcprof is disabled during timing. Every invocation edits a used Rust value, with a fresh client and an already primed engine and project cache. Cargo uses incremental Rust 1.77.2 and eight workers.

The engine binary is `a75afeec2c7fa014af451b8ba2eb87f1273990a83b2a5e45944031dd9da4aeaa`, from snapshot-source head `19eda9248` with the recorded 37-source overlay. Its installation preserves the cache volume and follows a clean exit; the previous binary takes 167.191 seconds to stop. That maintenance interval is outside the timed commands.

| Cohort | Command | Shell median | Native median | Cargo median | Median paired saving | Faster pairs |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| paired | 130-crate direct check | 0.717 s | 0.722 s | 0.126 s | -5 ms | 4/8 |
| paired | 1,026-crate grouped check | 1.964 s | 1.789 s | 0.837 s | 199 ms | 7/8 |
| paired | small workspace tests | 1.128 s | 1.021 s | 0.534 s | 126 ms | 6/8 |
| crossover | 130-crate direct check | 0.752 s | 0.851 s | 0.130 s | -159 ms | 2/8 |
| crossover | 1,026-crate grouped check | 2.395 s | 2.014 s | 0.800 s | 117 ms | 6/8 |
| crossover | small workspace tests | 1.108 s | 1.091 s | 0.521 s | 11 ms | 4/8 |

The confirmation exchanges physical source/cache histories. All admitted samples remain included, including 14.104- and 15.503-second shell samples and a 5.957-second native sample. Host I/O pressure reaches 55% in the confirmation despite quiet admission windows. Large-check engine-cgroup CPU medians are 1.762 → 1.772 seconds in the first cohort and 1.778 → 2.559 seconds in the confirmation. The native module is not selected globally: its control and CPU results remain mixed. The seven-line buffer improvement is established by the isolated component comparison; the command tables compare discovery implementations.

## What the diagnostic captures establish

Eight wcprof captures contain zero dropped events or open operations. Native discovery takes 188–191 ms in the two large captures, including a 154–155 ms filesystem fingerprint. Shell discovery takes 205–250 ms. Check execution and source-import variation account for additional differences in the complete commands.

The 130-crate direct control never calls the new fingerprint operation. One native-version control spends 136 ms in a directory digest, versus roughly 44 ms in the other controls. Another spends 833 ms importing sources. Those observations locate the control variability; they do not establish the cause of the long unprofiled samples. `dang.invoke` includes nested helper and engine work and must not be read as interpreter CPU time.

Exact reuse remains intact in both physical histories: 130/130, 1,026/1,026 and 6/6 compiler actions, with the expected execution markers in the retained batch. These unchanged calls verify correctness only.

Time-filtered Docker log recovery with a tail limit returns no historical records; removing the tail limit exceeds the 45-second read budget without records. Direct bounded-file recovery is unavailable under the host file permissions. The slow samples remain unexplained; no engine fix is claimed from them.

Evidence: [fingerprint-buffer](experiments/fingerprint-buffer/).
