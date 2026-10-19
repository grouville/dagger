# perf(go): share generation matching during package discovery

Package discovery includes generation-only packages, even when listing tests. Each Go module currently takes the same workspace-wide Go-file glob and maps its files to directory names again. On dagger/dagger this repeats across 80 modules; source-labeled CPU profiles identify it as the largest interpreted reduction.

Prepare those matches once inside `Go.packages` and pass the immutable value to its transient discovery objects. Each module still finds its own generation directives and applies the same include/exclude rules. Standalone generation uses its own workspace and settings. The glob algorithm and collection getter classes are unchanged, and the prepared value is not stored in collection results.

Complete `dagger check --module go --check test --list --all` on real dagger/dagger:

| Edit | Before | After |
| --- | ---: | ---: |
| Test file | 9.28 s | 7.33 s |
| Ordinary source | 5.91 s | 4.16 s |

Four balanced pairs per workload, faster in all eight pairs. Each command starts a fresh CLI on the same warm development engine and returns the same 4,398 ordered rows, including normal telemetry and successful cleanup. Test-edited profiles retain all 800 getters and 799 unchanged discovery hits; SDK requests fall from 1,494 to 1,415. Ordinary-edit CPU falls from 25.17 to 11.05 CPU-seconds and allocation from 5.15 to 2.07 GB.

The one-module fixture is flat at about 0.57 s, with 1.3 MB more allocation. Sixteen-module results are mixed; they do not establish a reliable small-repository latency improvement. An earlier version added a shared-library API and consistently slowed the small cases. This version shares the value locally and adds no API requests, engine changes, builtin or lock.

Twenty-five existing check invocations pass, including discovery, ownership, selected test execution, binaries, generation globs, exclusions and cwd behavior. The new regression passes before and after the change and checks nested modules, source removal, independent settings and workspace restoration. All 68 commands in the final timing protocols succeed.

This is a follow-up on the indexed-owner-facts prototype, not a standalone port validated against current upstream main. Cold listing and Rust latency are not measured. [Full evidence and retained alternatives](NATIVE_GO_GENERATION_MATCHES.md). No PR has been opened.
