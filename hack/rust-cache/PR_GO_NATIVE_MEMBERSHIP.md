# perf(go): use native membership for generation directories

Generation selection calls an interpreted equality callback for each candidate path. A real dagger/dagger listing performs 94,232 of these calls.

Use the existing `List.contains` operation for include and exclude lists. It uses the same string-equality implementation and changes two lines. This is part of reducing Go test collection listing overhead on dagger/dagger.

### Performance

Complete-command measurements use `dagger check --module go --check test --list --all`.

| Complete listing after a fresh edit | Before | After | Faster pairs |
| --- | ---: | ---: | ---: |
| Test file | 7.63 s | 7.44 s | 6/8 |
| Ordinary source | 4.40 s | 4.17 s | 3/4 |

Test-edit timing uses a fixed eight-pair follow-up: **2.5%** lower column median, with **111 ms median paired saving**. A slower candidate outlier remains included. Ordinary-source timing uses four pairs.

Each command starts a fresh CLI on the same warm experimental engine and includes telemetry and successful cleanup. All 44 real-repository commands across the initial screen and follow-ups return matching rows. Profiles retain all 800 getters and existing per-package discovery hits.

### Validation and tradeoffs

The 27 Go checks and 44 one-/sixteen-module timing commands pass, covering generation exclusions, edits, selected execution and workspace restoration. Small-workspace results are mixed: the sixteen-module screen is **0.746 → 0.893 s**, while its fixed follow-up is **0.744 → 0.694 s**. No uniform small-repository gain is established.

The patch adds no cache, engine change or selection rule. It removes interpreted callbacks using an existing operation.

**Draft:** the measured commit follows shared generation matching on the discovery prototype. Port and validate the two-line change on the intended upstream base before review; cold and Rust timings remain unmeasured.

[Measured commit](https://github.com/grouville/go/commit/720a5258ad8212ab643bbeaa4084127b2e866800). [All cohorts and reproduction](https://github.com/grouville/dagger/blob/experiment/rust-native-cache/hack/rust-cache/NATIVE_GO_DIRECTORY_MEMBERSHIP.md).
