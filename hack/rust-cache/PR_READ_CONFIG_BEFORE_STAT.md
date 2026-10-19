# perf(core): read host module config before a redundant stat

The engine reads a module's current `dagger.toml` to include its Git-client declarations in the call's cache key. Local modules first stat the file, then read it over the host connection. Go collection expansion repeats those two requests thousands of times.

Read first. A successful read already supplies the required current bytes; a missing file counts as absent. Other failures retain a stat fallback to distinguish directories from unreadable files. This is part of reducing Go test collection listing overhead on dagger/dagger.

### Performance

Complete-command measurements use `dagger check --module go --check test --list --all`.

Configuration requests fall **6,890 → 3,526**. Complete listing on the same warm experimental engine:

| Fresh edit | Before | After | Reduction | Faster pairs |
| --- | ---: | ---: | ---: | ---: |
| Test file | 7.04 s | 6.69 s | 5.0% | 3/4 |
| Ordinary source | 4.21 s | 3.93 s | 6.7% | 4/4 |

Each command starts a fresh CLI and includes telemetry and successful cleanup. All 24 commands return matching rows. Profiles retain all 800 package getters and existing discovery hits. These are edited, warm-engine comparisons, not cold-start or stock-release timings.

### Validation and tradeoffs

Focused core race checks pass. The single-request regression fails with the original stat-first order. All seven existing Git-client integration cases pass before and after, including config removal invalidating reuse and credential isolation. The 27 Go checks and 28 Rust/native-cache cases have their expected outcomes.

The full core suite remains red on this host because Git lacks `--ref-format` and a configured signing key is unavailable. Those failures are retained.

The patch adds no cache or lock. Config changes and removals remain live reads; failed reads may still need the existing stat fallback.

[Source](https://github.com/grouville/dagger/tree/experiment/read-config-before-stat). [Measurements, commands and failed attempts](https://github.com/grouville/dagger/blob/experiment/rust-native-cache/hack/rust-cache/NATIVE_READ_CONFIG_BEFORE_STAT.md).
