# Scoped Go search and workspace correctness, October 19

This follow-up checks the existing workspace-search contract and a replacement for the file-by-file discovery in [Go draft #68](https://github.com/dagger/go/pull/68). The published Go draft is still marked as blocked by a filename regression. The scoped replacement below is experimental and has not replaced that draft's source.

## Why the workspace change follows the existing design

Host-side search is intentional. So is including files created or changed through Dagger: Alex's original [overlay-aware search change](https://github.com/dagger/dagger/commit/e090829bb536bc83ab980efee4b301bbdf908459) explicitly describes both created files and applying explicit search paths to them. Its integration test already checks a new file inside an existing host directory. The later [mount-path fix](https://github.com/dagger/dagger/commit/a5b1708fe415c37982f67718016c0067ed3c65b2) handles the analogous problem for mounted paths that are absent from the source tree.

The remaining failure is a scoped search of a file or parent directory created only through Dagger edits. Dagger asks the host to search that missing path and errors before combining the host and edited content. [Draft #14740](https://github.com/dagger/dagger/pull/14740) filters those operands and performs the existing merge even when no host paths remain. Host execution, client scoping and errors for unrelated missing paths stay in place. This is a correctness fix; no performance gain is claimed.

The submitted real-CLI integration test has four cases. On the unchanged main engine, the added-file, new-parent and mixed-source cases fail; the unrelated-missing-path control passes. All four pass on the fixed engine. The baseline engine is `80699ac67a`; the separately built engine is `c5456d9cbf` plus this fix, with stock dependencies. The published PR was rebased onto `ce6dc9f940`; both changed file blobs exactly match the tested files. The diagnostic helper-level regression is retained here but is not submitted: the real-CLI test covers the same behavior. Existing focused source-path and merge tests pass under the race detector.

The draft description now links the original design and existing upstream test. Existing engines, volumes, cache policies and telemetry are preserved.

## Package-scoped Go discovery

The first file-by-file version errors on the valid filename `bracket[1]_test.go`. Searching a Dagger directory snapshot did not preserve that filename either. The replacement searches each package directory with a glob for its direct test files, retaining the existing matcher, ordered file filtering and directory traversal. It skips symlinked test files just as main does. A real check verifies an added host-workspace test and a newly created package; that last case requires the separate workspace fix above. The existing collection check, including selected execution and expected failures, passes.

The frozen `scoped-benchmark-source.patch` is against Go main `334136faaa`. Both timing arms use the same unchanged engine `80699ac67a`, with stock Dang and no other Go changes. Each arm has its own fixed Git root and configuration. Every measured invocation renames a test function, edits ordinary source and starts a fresh CLI. All expected names, row order, successful exits and cleanup are checked. These are warm-engine complete commands, with normal telemetry enabled and wcprof disabled during timing:

```sh
dagger check --module go --check test --list --all
```

| Fixture | Main median | Scoped median | Faster pairs | Engine allocations, main → scoped |
| --- | ---: | ---: | ---: | ---: |
| 16 packages, 128 tests | 12.15 s | 7.55 s | 3/4 | 6.88 → 3.99 GB |
| 1 package, 8 tests in 1 file | 1.995 s | 1.970 s | 2/4 | 719 → 704 MB |
| 1 package, 128 tests in 16 files | 3.454 s | 3.507 s | 1/4 | 1.65 → 1.64 GB |

The many-package comparison allocates about 42% fewer bytes and uses 48.50 → 28.38 engine CPU-seconds. Allocation is cumulative, not peak resident memory. Timing remains variable: an identical-code, two-pair control measures 13.08 → 10.21 s despite using main on both sides. The one-package, 16-file control has a median paired slowdown of 459 ms, distinct from its 53 ms difference between separate column medians. That control's CPU and allocation medians are essentially unchanged. These observations must accompany any latency claim; they do not establish the current full dagger/dagger listing time or a cold-start gain.

Separate wcprof captures confirm the work removed: both versions execute 18 workspace searches, while matched-line reads fall from 2,176 to 256. Those are result reads, not 2,176 host search processes. Both captures have zero dropped events and zero unfinished operations. Raw compressed profiles remain local, with hashes recorded here; counts and text reports are included. The first profile harness attempt rejected valid output because it assumed single spaces in the CLI table; that attempt is retained, and the corrected parser uses whitespace-separated columns.

The source has not yet replaced Go #68. Keep the known filename issue visible on that draft, and resolve the controls and remaining compatibility review before promoting the replacement. No timings from the earlier file-by-file implementation are attributed to this source.

A further directory-name probe stores a module in `module[1]`. Both main and the candidate fail during workspace file import, before test-name discovery, with the same filesync error. Those failures are retained and are not timing samples or proof of compatibility. Literal directory names still need review before promoting the replacement.
