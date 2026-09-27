# CLI metadata: collection and real input invalidation follow-up

All 15 local CLI invocations met their expected outcomes; two are deliberate stale-function errors. No Cloud requests were enabled. The original engine and both fixtures were restored, and the engine was stopped.

The corrected engine includes both public collection type closure and equivalent root-demand handling for the JSON metadata endpoint. The old and new CLI use the same engine and retained volume. The baseline CLI uses the existing GraphQL metadata projection; the candidate uses the JSON projection.

- Collection get returns exactly all six expected test names on both CLIs; subset returns exactly the dot module key. Output bytes match between CLIs. These are metadata/collection probes, not test execution. The first baseline collection call can pay setup and warm shared state for the following candidate call; their durations are not a matched performance comparison.
- Renaming the same native module method from read to readEdited makes read-edited callable on both CLIs, while both reject the stale read name. Restoring the complete original module bytes makes candidate read work again.
- Four separately edited input payloads produce their exact new bytes. Each measured command receives a distinct UUID payload with no prior call on those bytes. Unchanged lower layers can still use ordinary Dagger caching.

| Fresh-input pair | Order | GraphQL CLI | JSON CLI | Difference |
| --- | --- | ---: | ---: | ---: |
| 1 | baseline → candidate | 0.445 s | 0.293 s | -152.1 ms |
| 2 | candidate → baseline | 0.443 s | 0.305 s | -138.1 ms |

The two-sample medians are 0.444 s and 0.299 s (32.6% lower for the candidate). This is a narrow native-module read after input edits, with n=2 per CLI. It is not a reliable estimate across projects, a cold-start result, or a full greetings check/listing benchmark. Neither primer nor renamed-schema/error timings are pooled into this comparison.

Timing covers CLI process spawn through blocking waitpid completion. Setup, engine startup, resource snapshots and final restoration are outside that interval. No profiler was enabled. Engine CPU, IO and host pressure deltas are included as contextual counters; they do not independently identify the cause of the latency difference.

The failed v1 trial is retained separately. It repaired the original collection closure error but exposed a missing workspace-loading trigger in the JSON endpoint. Its faster rejected candidate call is excluded. The corrected trigger preserves both full-schema and client-scoped module loading instead of unconditionally loading every module.

The archive is an explicit allowlist: source driver, evidence builder, numeric outcomes and hashes. It contains no stdout/stderr, raw profiles, engine binaries, container/client IDs, endpoint URLs, authentication data or private Cloud code.
