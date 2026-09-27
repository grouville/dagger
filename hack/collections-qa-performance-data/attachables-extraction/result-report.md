# Attachables extraction: validated startup result

The isolated package extraction reduces the heavy helper's warm host-process startup. **Twelve alternating pairs measured 9.114 → 6.357 ms median**, with a median paired reduction of **2.796 ms**; all 12 candidates were faster. This is a process-startup measurement, not an engine/CLI discovery speedup.

| Observation | Original heavy helper | Extracted heavy helper |
| --- | ---: | ---: |
| Ordinary startup/exit median, n=12 | 9.114 ms | 6.357 ms |
| Ordinary range | 8.742–10.512 ms | 6.202–6.514 ms |
| Binary bytes | 47,976,610 | 41,681,058 |
| Static transitive package count | 1,228 | 856 |
| Separate inittrace records | 505 | 365 |
| Separate inittrace reported allocation bytes | 3,407,400 | 2,252,128 |

Both binaries used the same source/dependencies, Go 1.26.6, linux/amd64, CGO disabled, tags `dfexcludepatterns,dfparents`, and `-s -w`. They retain the original combined PID1/helper program: **no split-init/light PID1 was combined into this comparison**. The only candidate change is the attachables package extraction. Exact hashes and commands are in the build manifest.

The driver ran four warm-up processes, 12 alternating pairs, and two separately instrumented processes, all successfully. Both binaries received an unmatched argv[0], so their main switches exited before PID1/session behavior. Timing covers Popen through the owned child's actual wait4 completion, with a bounded timeout and joined reaping; no polling granularity is inside the duration. Host page caches stayed warm. No Docker, engine, Cloud or network-runtime calls occurred.

The two inittrace runs are diagnostic observations excluded from ordinary medians. Their package clocks are not predicted CLI savings. ru_maxrss was exactly 66,768,896 bytes for both binaries; this inherited launcher/pre-exec high-water measure is unsuitable for comparing their memory use and is retained only as raw data.

Five focused gates passed before building: the original filesync/parent-directory metadata/client lifetime tests; extracted filesync/search/atomic export/parent metadata plus socket-policy/real Unix half-close tests normally and under the race detector; and legacy aliases/server registration plus real client upgrade/cancel/shutdown lifetime tests normally and under race. The old package's test remains an alias compile witness, not an external consumer test. Both cmd/init builds succeeded, and the temporary empty overlay package directory was removed.

The move keeps filesync/socket/server function bodies and all secret/Git/h2c providers. Exported aliases and wrappers preserve ordinary Go source API use. Concrete types now have the new defining package under reflection; that remains an explicit compatibility consideration. No cache policy, TTL, filesystem snapshot authority or provider behavior was changed intentionally. A small real Go/TypeScript/Python nested-session smoke is still needed before production adoption.

History is retained: the first package-list attempt was blocked by a read-only metadata cache and is invalid evidence; the second static graph capture succeeded. Independent review then found a missing instrumentation-scope constant before compilation. It was added with the original `dagger.io/engine.client` value and an equality witness. The first source-only archive remains unchanged. No behavioral gate failed in the corrected run.

This is a tested, isolated follow-up with a modest startup win. Shared production source is unchanged, and no whole-command improvement is claimed.
