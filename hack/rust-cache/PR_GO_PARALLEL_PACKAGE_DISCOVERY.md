Go package discovery currently waits for each module before starting the next. On a large workspace, those independent reads form a serial chain before test collections can expand.

Use Dang's ordered parallel selection to discover per-module paths, then concatenate the returned lists. Existing filtering, sorting and collection granularity are preserved.

For `dagger check --module go --check test --list --all` on dagger/dagger:

| Order | Before | After |
| --- | ---: | ---: |
| Before, after | 85.35 s | 72.37 s |
| After, before | 86.27 s | 70.11 s |

All four commands return the same 4,398 rows and exit successfully. Each starts a fresh CLI and edits a source comment; the engine is warm, with telemetry and normal GC enabled. The engine includes other performance experiments held constant across both arms. This measures the module change, not a comparison against stock upstream Dagger.

The first candidate performs 801 additional session flushes on its first full-repository use. In the reverse comparison both perform the usual number of invocations: allocated bytes are 43.64 GB in both and engine CPU decreases from 292.14 to 285.08 seconds. A separate wcprof comparison places the package-discovery phase at 42.51 → 27.57 seconds; it includes awaited API calls.

Focused ownership and test-collection checks pass, covering nested modules, overlays, Unicode, selections and ordering. The final change passes the Dang v2 formatter. The full listing remains slow; this removes one serial discovery chain.
