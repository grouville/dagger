# Reuse parsed syntax after a module remount

The experimental [bounded parsing cache](NATIVE_PARSE_CACHE_BOUNDED.md) included
the absolute filename in its key. Releasing a module's temporary read-only mount
and mounting the same snapshot again gives it a new path. Identical source then
missed this cache and ran the parser again.

Six fresh edited Rust commands expose this directly. Parsing takes 79.5, 2.4,
2.7, 79.4, 2.8 and 2.4 ms. Engine debug lines show one mount path for the first
three commands and another for the last three. The library remains bounded;
the misses are caused by changing paths, not changing code.

The new variant keys construction instructions by source bytes. Each use supplies
the current filename when constructing `SourceLocation` values. Ordinary string
literals stay unchanged, including literals containing an old path. Reading the
file, type inference, import resolution and evaluation still happen for the
current call. No schema, client or evaluated value is retained by this cache.
The 128-entry and 64 MiB construction-weight limits remain in place.

This refines our own parser-cache prototype. It is not a standalone bug fix
against an existing upstream parser cache. The library change stays isolated;
no dependency update or upstream PR has been opened.

## Verify a real remount

Two engines use the same engine overlay, dependencies, build settings and Rust
module (`a8ede44`); only the local Dang library differs. The normal command is
`dagger check rust:check` on the 130-crate root-package fixture. Each capture
follows a new leaf edit. Telemetry stays enabled.

After one capture per engine, a 31-second idle interval exceeds the mounts'
30-second retention period. Both engines demonstrably use different module
mount paths on the next command. All four captures are complete, with no dropped
events or open operations:

| Parsing phase | Filename key | Content key |
| --- | ---: | ---: |
| First capture | 85.15 ms | 2.73 ms |
| After idle mount expiry | 80.43 ms | 2.88 ms |

This demonstrates syntax reuse after a remount. A completely cold syntax cache
still parses source once. These are diagnostic phase durations, separate from
the complete-command timing comparison.

## Component cost and correctness

The component benchmark uses the actual Rust module source and cycles through
64 file paths. Files are prepared before timing. Each variant has its own fresh
128-entry, 64 MiB cache. Medians across three runs:

| Case | Filename key | Content key | Allocation before | Allocation after |
| --- | ---: | ---: | ---: | ---: |
| Paths rotate | 93.16 ms | 2.56 ms | 31.72 MB | 0.725 MB |
| Stable path | 2.511 ms | 2.548 ms | 724,496 B | 724,512 B |

The stable-path case adds one allocation for the current filename. An initial
prototype allocated it for every source location (2,322 extra allocations);
the final variant creates that value once per construction. Both sets of
candidate samples are retained in the data.

The regression checks one retained entry across four paths, equality with fresh
syntax at each path, and isolation from caller mutation. It fails against the
filename-key implementation, which retains four entries. Separate checks verify
relative imports resolve in the current directory and inference diagnostics name
the current file even after the earlier file is removed. The language and
type-inference packages pass under race detection, including the Rust module
corpus and the existing schema/client/concurrent-evaluation tests.

## Complete-command results remain mixed

Eight alternating pairs per scenario use warm engines, independent source trees,
native histories and Cargo targets. Invocation order rotates. Every command
has a distinct new edit, including separate values for each variant. Telemetry
is enabled; wcprof is disabled. The timer uses blocking `waitpid`. Preparation
commands are excluded. Native Cargo uses the same Rust 1.77.2 toolchain and
eight jobs.

| Scenario | Filename key median | Content key median | Cargo median | Median paired saving | Faster pairs |
| --- | ---: | ---: | ---: | ---: | ---: |
| Leaf edit | 0.948 s | 0.781 s | 0.109 s | 1 ms | 4/8 |
| Shared-library edit | 1.557 s | 1.477 s | 0.607 s | 21 ms | 5/8 |
| Actual package test collection | 1.045 s | 1.278 s | 0.509 s | −23 ms | 4/8 |

The binaries are then swapped between the same engines, preserving their cache
volumes. A later shutdown audit shows that Docker's 30-second stop timeout
force-killed one engine during this swap. Its startup intentionally reset the
unclean worker and DAGQL stores. Four preparation rounds precede eight further
pairs, but the comparison does not preserve both original histories:

| Scenario | Filename key median | Content key median | Cargo median | Median paired saving | Faster pairs |
| --- | ---: | ---: | ---: | ---: | ---: |
| Leaf edit | 0.932 s | 0.829 s | 0.122 s | −34 ms | 4/8 |
| Shared-library edit | 1.687 s | 1.565 s | 1.166 s | −5 ms | 4/8 |
| Actual package test collection | 1.484 s | 1.264 s | 0.503 s | 321 ms | 5/8 |

Column medians and median differences within pairs answer different questions.
Neither series establishes a consistent full-command benefit. Host I/O stalls
reach 88.9% in the first series and 82.8% in its crossover. All samples remain,
including 6–8 second Dagger commands and a 6.743-second Cargo shared edit. The
controlled remount and component results support the mechanism; the latency
target still needs a less variable confirmation.

Post-series probes recover 130/130 compilation results and 6/6 collection results
on both engines. The collection's last application edit has four compilation
markers. After the controlled remount, each leaf edit has exactly two markers
and its next probe recovers all 130 results. Cargo logs check the expected two
or 130 crate rebuilds. No steady-state improvement is assigned to this variant
in the selected performance stack.

The final binary restoration also force-kills the other engine at the same
30-second deadline. The initial restart probe correctly reports zero reuse
after its intentional cold reset; the other engine recovers 130/130. This is
a harness failure, not evidence of source-hash corruption or of the parser
variant invalidating compilation results. The audit records SIGKILL, exit 137
and `dagql_unclean_shutdown` in the startup log.

The corrected restart helper waits for session teardown, stops without a forced
kill deadline and requires exit 0 before restarting or replacing the binary.
After warming the reset engine, this controlled stop exits 0 in 7.0 seconds;
the subsequent probe recovers all 130 native results. The component and
controlled remount findings stand. No complete-command gain or preserved-history
crossover is claimed for this library experiment.

The [library delta and reproduction](experiments/dang-parse-content-key/README.md),
[component samples](experiments/dang-parse-content-key/component.json),
[complete-command samples and pressure](experiments/dang-parse-content-key/commands.json)
and [controlled remount captures](experiments/dang-parse-content-key/mounts.json)
preserve the evidence.
