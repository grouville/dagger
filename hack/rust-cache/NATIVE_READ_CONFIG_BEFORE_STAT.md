# Read host module configuration without a preliminary stat

The candidate removes a redundant engine-to-host request while retaining live configuration reads and the existing declaration checks. Complete listing on real dagger/dagger improves in both edit workloads:

| Complete command | Stat then read | Read first | Faster pairs |
| --- | ---: | ---: | ---: |
| Test-file edit | 7.04 s | 6.69 s | 3/4 |
| Ordinary-source edit | 4.21 s | 3.93 s | 4/4 |

Both modes use Go module `720a525` and the same development engine binary. A fresh CLI receives a real edit on a warm engine. Normal telemetry, ordinary GC, output, final flushing and successful cleanup are included. Both versions complete test addition and removal before four alternating measured pairs per workload. All 24 timing commands return the correct ordered rows and exit successfully. The stable listing has 4,398 rows. The slower test-edit candidate pair is retained; the median paired saving is 413 ms. These cohorts are separate from previous results, without pooling or additive savings. Cold, released-engine and Rust latency effects are unmeasured.

| Engine work | Test edit, before → after | Ordinary edit, before → after |
| --- | ---: | ---: |
| CPU-seconds | 29.06 → 27.94 | 10.78 → 10.16 |
| Allocated bytes, decimal GB | 6.333 → 6.317 | 1.930 → 1.896 |

An audit of the preceding source-edit profile found 3,364 successful stats of the Go module's `dagger.toml`, plus 162 checks of its missing nested config. Their aggregate parallel duration is not elapsed time or promised savings. They come mainly from checking Git-client declarations while preparing module calls and computing their cache inputs, rather than from importing the project's source.

The host reader used to stat each path and then read it when present. It now reads first. Success supplies the required current bytes; a missing-file status reports no file. Other read failures fall back to stat so directories still count as absent and unreadable files retain their errors. Each lookup reads again. The parser, nearest-config search, declaration digest, session binding and unreadable-result invalidation remain. No content cache, sharing of clients, new lock or dependency is added. The small private backend interface makes the reader testable without a live engine.

Both before/after workload captures confirm the mechanism:

| Configuration requests between engine and host | Before | Read first |
| --- | ---: | ---: |
| Stat | 3,526 | 0 |
| Read | 3,364 | 3,526 |
| Total | 6,890 | 3,526 |

The additional reads are the same 162 missing paths previously checked by stat. Other workflows can still use the fallback stat. SDK request counts stay at 1,415 after a test edit and 493 after an ordinary edit. Test-edited profiles retain 804 evaluations, all 800 authored getters and 799 unchanged test-discovery hits. Ordinary-source profiles retain all getter and discovery hits. All four captures are lossless and close every operation.

Focused reader race checks pass on the standalone source and the exact engine overlay. Tests cover changed and empty contents, missing files, directories, read/stat errors and cancellation. The single-request regression fails with an equivalent helper using the original stat-first order. The broader standalone core run is not green: Git 2.43 lacks `--ref-format`, and a signing test cannot find the configured private key. Those failures are retained and are not reported as passing checks.

The existing Git-client integration passes all seven cases in both modes. It verifies declared and undeclared clients, local and Git-loaded modules, a removed declaration invalidating a cached result without changing the module's implementation digest, a plain program's own credentials, and another session without credentials. The 27 Go check invocations and 28 Rust/native-cache cases also retain their expected outcomes, including selected execution, required failures, edited/restored sources and native compilation-action hits. No Rust speedup is claimed.

The integration harness required corrections before it could test either mode: the older engine checkout has an unrelated test compilation error, the benchmark CLI is dynamically linked and cannot run in Alpine, and nested CLI versions must agree with bootstrap metadata. The successful test uses the clean main-based checkout, a static CLI, and the supported per-exec version override. All assertions are unchanged. Failed attempts and exact fixture overlays are preserved. Listing measurements keep the original pinned benchmark CLI and engine binary. An integration-generated lockfile was saved and restored before committing.

[Standalone source](https://github.com/grouville/dagger/commit/98d6b5c3f3c6b572bbf8d5712cb7ecb9276e7c8c) is based on upstream `ff0b029a4d270a651b9a8c7286babc79089066e4`. The [PR description](PR_READ_CONFIG_BEFORE_STAT.md) is prepared; no PR is open. [Evidence](experiments/read-config-before-stat/) includes all attempts, checks, raw timings, four lossless captures, source patches and exact engine inputs. All thirteen engines and cache volumes remain intact, workspaces are restored, the reader experiment is off, and capture switches are restored. The three-second full-pipeline goal remains unfinished.
