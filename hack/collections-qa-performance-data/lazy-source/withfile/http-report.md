# Strict HTTP execution follow-up

All four fresh HTTP checks passed, including the exact new revision header, with complete source restoration. The unprofiled pair was **11.464 s control → 11.412 s candidate**. A separate pair with wcprof, run in reverse order, was **11.545 s → 10.723 s**. These are one ordinary pair and one profiled diagnostic pair; do not pool them or present them as a performance distribution.

Both pairs use new response-header bytes and matching E2E assertions, identical between variants. The test's missing-URL skip is converted to a fatal failure. A stale backend binary cannot satisfy the new header assertion. The same pinned CLI and engines are checked before use. Both engine volumes are retained and have different histories; this is a local-only edit/execution diagnosis, not a cold-start comparison.

## The necessary build still runs

| Profiled command | Control | Candidate |
| --- | ---: | ---: |
| CLI completion | 11.545 s | 10.723 s |
| Go-build process count | 1 | 1 |
| Go-build process duration | 7.964 s | 7.953 s |
| `otelgotest` process count | 1 | 1 |
| `otelgotest` process duration | 0.706 s | 0.454 s |
| Recorded operations | 8,640 | 8,639 |
| Open / dropped records | 0 / 0 | 0 / 0 |
| Operations outside CLI bounds | 0 | 0 |

The important change is where the build happens. In the control, the Go-build process is beneath an eager `call_exec:Container.withFile`. In the candidate it is beneath the lazy chain:

```
service.start
  → Container.withExposedPort
    → Container.withEntrypoint
      → Container.withFile
        → Directory.file
          → Directory.withFile
            → Container.file
              → Container.withExec
                → go build
```

The candidate therefore still materializes the binary when the service is actually consumed. It does not turn an HTTP test into a metadata-only or cached-success substitute. The roughly eight-second backend build remains necessary in these fresh execution cases; the listing optimization moves that work out of discovery rather than removing required execution.

Build process starts are 1.709 s into the control CLI and 1.811 s into the candidate. The test processes start at 10.734 s and 10.137 s respectively. Full parent chains, counts and capture bounds are in `http-profile-proof.json`. Nested durations overlap; they are not an additive latency budget. The 0.822 s profiled CLI difference is not explained solely by the almost identical build intervals.

## Resource observations

Counters are taken outside the CLI timer and cover a slightly wider bracket. Engine CPU/I/O include child and background work; PSI is host-wide. Values below are decimal MB.

| Pair / variant | CLI s | Engine CPU s | Read MB | Written MB | Host I/O PSI `some` ms | Host CPU PSI `some` s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Ordinary control | 11.464 | 41.44 | 54.15 | 85.77 | 93.12 | 1.80 |
| Ordinary candidate | 11.412 | 42.12 | 4.63 | 0.31 | 13.18 | 2.08 |
| Profiled candidate, first | 10.723 | 42.49 | 0.46 | 0.31 | 9.85 | 1.77 |
| Profiled control, second | 11.545 | 42.44 | 57.89 | 0.31 | 141.56 | 1.79 |

The CPU work is similar across all four calls. The observed host I/O stalls in this follow-up are below 0.15 seconds per bracket. Read/write counters differ, but retained page/cache state and delayed writeback can affect when bytes are charged. These short brackets do not establish total storage work or prove an I/O reduction from the patch. No engine CPU throttling was recorded.

## The original long sample stays unresolved

The first strict HTTP pair in the earlier run was **13.599 s control versus 26.581 s candidate**. Those two original rows have no wcprof or resource-counter brackets, and the candidate/control volumes had unequal prior histories. Their latency cannot now be attributed to disk stalls, cold compilation, duplicate work or the lazy patch from this newer evidence.

The fresh follow-up did not reproduce that large difference, and its complete profiles show one required Go build in each variant. This supports correctness and identifies the execution dependency, but it does not justify a blanket no-regression guarantee or deleting the original outlier. Keep both the original pair and this follow-up in the report.

The shareable files contain only numeric results, hashes, operation classes and aggregate dependency chains. Raw profiles, process command metadata, stdout/stderr and source payloads remain outside the archive allowlist.
