# CLI listing complexity and broader UX regression matrix

September 25, 2026. The 500 ms target concerns user-visible Dagger overhead:
navigation/listing response, getting an actual check or generator started, and
getting a service ready. A slow user test/build remains a distinct execution
cost. Both total latency and startup latency must stay visible.

## Generic change

`listArtifactSelection` used `len(listedArtifactKeys(items)) > 0` to decide
whether output needed dimension aliases. That constructs and deduplicates the
entire key union, then discards it. `--all` subsequently prints individual rows,
so no full union was otherwise required. The new guard scans until the first
item containing a key and allocates nothing. The no-key case scans all items.

Real key unions remain necessary when grouping filtered rows. They now keep
first-occurrence order in a slice and create a membership map only after eight
distinct pairs. Pair identity includes both dimension and key. Small rows keep
the allocation-free membership scan; large unions take expected O(K) work
instead of O(K²). Empty keys, aliases, input ownership, order, filtering and
printed commands are preserved. No cache survives the current function call.

The common formatter serves `check -l`, `generate -l`, `up -l`, and the other
command-specific artifact listings. `dagger list` has its own formatting path;
it is included in the regression matrix but is not directly accelerated by this
patch. `dagger ws ls` lists workspace files, not artifacts.

## Actual CLI formatter benchmark

Six alternating before/after pairs exercise `listArtifactSelection` itself:
JSON decoding, grouping, global dimension aliases, rows and command output.
An in-memory SDK transport deliberately excludes engine, Cloud and network
time. Both test binaries contain the same tests and benchmark; an overlay
replaces only the baseline `artifact_list.go`. Fresh processes, Go 1.26.6,
GOMAXPROCS=8, 250 ms benchmark duration per size, no concurrent engine workload
or build. Values are medians, not end-to-end CLI latency.

| Expanded elements | Before | After | Ratio |
| --- | ---: | ---: | ---: |
| 14 | 0.167 ms | 0.171 ms | Flat within observed variation |
| 100 | 0.736 ms | 0.676 ms | 1.09× |
| 1,000 | 9.499 ms | 5.799 ms | 1.64× |
| 10,000 | 415.518 ms | 59.986 ms | 6.93× |

At 10,000 elements, allocated bytes fall from 31.79 to 29.95 MB per listing.
This removes a genuine scaling problem. It does not account for the seconds
remaining on a 14-row greetings-api listing. Focused tests pass on both
binaries, including global alias ambiguity, nested collections, explicit
filters, empty keys, shell quoting and nonmutation. Boundary tests exercise
the small-row/index transition and repeated keys in different dimensions.

## End-to-end measurements

`ux.py` covers greetings-api artifact overview, static and
expanded check listings, filtered selection, type/collection navigation,
dynamic help, generator/service listings, workspace files and a real selected
check. All commands start a new CLI and include exit. The driver now has an explicitly audited local-only mode; Cloud-enabled runs remain a separate, pending scope.
Warm comparisons alternate order; source edits in this driver are correctness
probes only, since the first run can prewarm identical content for the second.

`vertical.py` adds an independent native-Dang fixture for actual `check`,
`generate`, `up`, direct module calls, and actual host-file exports. It measures three boundaries:

- CLI spawn to selected producer/check execution, from separate wcprof traces;
- operation completion or HTTP readiness, with expected output checked;
- CLI exit, including shutdown under the recorded telemetry mode. For `up`, readiness is followed by
  SIGINT, and tunnel cleanup is checked independently.

Every timed edit in this second driver has unique source bytes and launches
the command immediately, with no intervening listing. The generator must
write the expected bytes, the service must return the expected HTTP body, and
a deliberately invalid input must fail the check before restoration passes.
The fixture contains negligible business logic so fixed orchestration costs
are visible. It does not replace SDK-specific Go/TypeScript/Dang coverage.

The 79-call native fixture preflight passed with a valid BusyBox HTTP server. The earlier Alpine service fixture lacked that command and is not a performance sample. A precision timing series uses a dedicated blocking waiter thread to avoid Python timed-wait polling tails. See the separate published UX report for results and bounds.

These runs use the existing retained experimental engine: Dang syntax cache,
prepared TypeScript runtime and static-TypeScript registration proof. They are
not a normal-build performance promise and are not fresh-volume cold runs.
The existing cold, compiler-cache and real HTTP e2e results remain separate.

## Reproduction

`build.py` creates frozen baseline/candidate CLI and test binaries; `measure.py`
runs the formatter comparison. Run `ux.py --run` and `vertical.py --run` only
while exclusively owning the selected benchmark engine. Both scripts default
to a dry run. `analyze_phases.py RESULT_DIRECTORY` correlates separate wcprof
captures with same-host CLI wall-clock anchors. Its residual completion-to-exit
time is not attributed wholly to telemetry without matching evidence.
