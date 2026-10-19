# perf(go): share generation matching during package discovery

Listing tests also discovers generation-only packages. Each Go module repeats the same workspace-wide Go-file glob and directory conversion. On dagger/dagger that work repeats across 80 modules.

Prepare immutable generation matches once inside `Go.packages` and pass them through its transient discovery objects. Each module still finds its own generation directives and applies the same selection rules. Standalone generation prepares matches from its own workspace and settings.

This is part of reducing Go test collection listing overhead on dagger/dagger.

### Performance

Complete-command measurements use `dagger check --module go --check test --list --all`.

| Complete listing after a fresh edit | Before | After | Reduction |
| --- | ---: | ---: | ---: |
| Test file | 9.28 s | 7.33 s | 21.0% |
| Ordinary source | 5.91 s | 4.16 s | 29.6% |

Four alternating pairs per workload; all eight improve. Each command starts a fresh CLI on the same warm experimental engine, returns identical 4,398 ordered rows, and includes telemetry and successful cleanup.

Profiles retain all 800 getters and 799 unchanged discovery hits. SDK requests fall **1,494 → 1,415**. Ordinary-edit CPU falls **25.17 → 11.05 CPU-s**, with allocation **5.15 → 2.07 GB**.

### Validation and tradeoffs

The 27 check invocations pass, including generation selection, exclusions, edits, nested modules, independent settings and restoration of an earlier workspace. The one-module control is flat around 0.57 s, allocating 1.3 MB more. Sixteen-module results are mixed.

Production code grows by 33 net lines. The shared value stays local to discovery; it adds no global cache, lock, engine API or stored getter state.

**Draft:** the measured commit follows the discovery prototype. Extract onto upstream Go module main and validate there before review; the numbers above are not measurements of that future port.

[Measured commit](https://github.com/grouville/go/commit/511d38145daf87b531e44ed9b1c3b641fbe89ba3). [Measurements and reproduction](https://github.com/grouville/dagger/blob/experiment/rust-native-cache/hack/rust-cache/NATIVE_GO_GENERATION_MATCHES.md).
