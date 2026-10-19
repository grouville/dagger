Draft: this needs dagger/dagger#14740 before merging. That fixes scoped searches of package directories created through Dagger in a host workspace. The new check passes on that engine and fails on current main.

This is part of the work to make Go test collection listing faster. To list one package’s tests, the module currently reads matching test lines from every package in the Go module, then keeps only the requested package’s files. Listing all packages repeats that work.

Search each package directory for its own test files instead. Keep the existing rules for recognizing test names and the same filename order. The module-wide search that discovers package paths stays in place.

Complete listing commands, comparing this change alone with Go module main:

| Workspace | Main | This change | Engine allocations, main → change |
| --- | ---: | ---: | ---: |
| 16 packages, 128 tests | 7.94 s | 6.16 s | 6.42 → 4.59 GB |
| 1 package, 128 tests in 16 files | 3.85 s | 3.68 s | 1.77 → 1.72 GB |
| 1 package, 8 tests in one file | 2.29 s | 2.27 s | 0.911 → 0.910 GB |

Six alternating pairs per workspace. The many-package case improves in five of six pairs; engine CPU falls from 42.04 to 31.98 CPU-seconds. The one-package controls establish little benefit. An identical-code control, also six pairs, measures 8.248 → 8.252 seconds, with three faster pairs on each side.

To keep the workspace and configuration unchanged, both versions are installed under separate aliases in the same workspace. Each command selects one alias with `dagger check --module <alias> --check test --list --all`. Each measured pair changes a test name. Each command edits source and test comments, starts a fresh CLI and checks all expected names, row order and successful cleanup. The engine is warm; normal telemetry is enabled and profiling is off during timing. Allocations are cumulative bytes allocated by the engine, not peak memory.

A separate wcprof capture explains the change: both versions execute 18 workspace searches, while reads of matching test lines fall from 2,176 to 256. No events are dropped and no operations are left open. Those counts are result reads, not thousands of host search processes.

Each package now has its own search scope. This removes repeated processing in modules with many packages; a single package has essentially the same work. Earlier comparisons in separate workspaces were more variable, including a slower single-package run, and are retained with the measurements. The full dagger/dagger attempt still reaches the 240-second cutoff without returning rows. The fixture improvement does not resolve the full-repository bottleneck, and these measurements do not establish a cold-start gain.

Both arms use unchanged upstream engine `80699ac67a` and Go main `334136faaa`, with only this Go change applied to the candidate. No new retained cache state is added. Checks cover literal filenames such as `bracket[1]_test.go`, symlink handling, mounted workspaces, Unicode names and files added through Dagger. The existing collection check also passes selected execution, package isolation, expected failures, nested modules, build constraints and ordering. Formatting passes.
