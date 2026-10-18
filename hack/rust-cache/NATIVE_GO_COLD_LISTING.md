# First Go collection listing with an empty engine cache

On three independent new engine processes with empty Dagger cache volumes, complete Go test listing takes **20.19 seconds median from engine start through command completion**, with a range of **19.98–21.93 seconds**. Engine readiness itself takes **0.55 seconds median**. The first listing accounts for most of the elapsed time. This is slower than subsequent edited listings and does not meet the three-second target.

The command is `dagger check --module go --check test --list --all`, on the real dagger/dagger checkout `ff0b029a4d270a651b9a8c7286babc79089066e4`. Every invocation starts a fresh CLI and edits ordinary Go source. Telemetry, ordinary GC, session cleanup and final log flushing remain included. No profiler or concurrent build/test runs during measurements.

| Scenario | Median | Samples |
| --- | ---: | ---: |
| Start a new engine and complete its first listing | **20.19 s** | 3 |
| First listing command alone | 19.61 s | 3 |
| Ordinary-source edit on that warmed engine | **5.85 s** | 3 |
| Add a real test on that warmed engine | **12.27 s** | 3 |
| Remove the added test, returning to cached content | 5.96 s | 3 |

The third and fourth commands verify a new row appears and disappears. All 12 commands exit successfully and return exactly the expected ordered names and complete row text: 4,398 rows normally and 4,399 after adding the test. The test-addition workload differs from the preceding comment-only test-edit cohorts; its latency should not be treated as a regression or gain against them. There is no before/after optimization comparison here.

## Meaning of cold

Each engine name and its named volume are verified absent before creation. Each process gets its own empty `/var/lib/dagger`; no retained engine or volume is reset. Docker image `af521f4a…` is already local and the host OS page cache is not flushed. Image download, cloning the source repository, Docker container creation and copying the diagnostic binary are outside the measured engine-start interval. This establishes first use with an empty Dagger cache, not a completely uncached machine. Restarting an engine with an existing on-disk cache is a different scenario and is not measured here.

Elapsed time starts before `docker start` and ends after complete CLI exit and final log flush; it also includes the short diagnostic configuration/readiness work. The measured engine remains running after each command, as normal daemon use does. After the four commands, the study restores workspace files and configuration, disables temporary switches and stops that engine gracefully before creating the next. All three stops exit zero without forced termination; volumes are retained.

## Stack and limits

All engines use the same selected development stack: engine SHA-256 `37d4c555e4c5bf4370f7aa70b653a53b576ba08fa9c615898bb03bff6b8eb122`, CLI `97f7d82dc2f7b3da203aa683971ea3658b6de6a8e9b968a44905e379f499f965` and Go module `09518aac0858390722e71c82a719c2f6e131e611`. Typed metadata, response projection, getter content identity and the two validated Dang fixes are enabled. The unselected shared-argument-metadata experiment remains disabled. Settings are Go 1.26.6, `goflags = "-p=8"` and `test = ["."]`. This is not released or stock-main Dagger.

Host CPU pressure reaches 27.6% and I/O pressure 8.2% across the commands. Three fresh caches give useful observations, not a universal cold-start guarantee. Listing starts no compiler or test execution. The original Go and Rust engines are not modified; their binary identities are verified afterward.

[The evidence archive](experiments/go-cold-listing/) contains the exact driver, configuration, activation records, all attempts and full outputs, CPU/allocation/pressure counters, successful source restoration and graceful stops. The next cold-specific profile should separate first discovery and module initialization from steady edited listing. The first-use result must not be substituted for warm timings or added to previous savings.
