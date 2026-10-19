# perf(core): avoid a preliminary stat when reading host module config

The engine rereads a module's governing `dagger.toml` to include its Git-client declarations in the call's cache key. For local modules it first stats the file, then reads it over the host connection.

Read first. A successful read supplies the required current bytes; missing files still count as absent. Other failures fall back to stat to distinguish directories from unreadable files. Configuration changes and removals are still observed on every lookup. No cache or lock is added.

On real dagger/dagger, configuration requests fall **6,890 → 3,526**, with all 800 authored getters and existing discovery hits retained. Complete listing with a fresh CLI on a warm development engine:

| Edit | Before | After | Faster pairs |
| --- | ---: | ---: | ---: |
| Test file | 7.04 s | 6.69 s | 3/4 |
| Ordinary source | 4.21 s | 3.93 s | 4/4 |

Timings include telemetry and successful cleanup; all 24 commands return matching rows. Focused core race checks pass. All seven existing Git-client integration cases pass before and after, including declaration removal invalidating cache reuse and credential isolation across sessions. The 27 Go checks and 28 Rust/native-cache cases have their expected outcomes.

The full core run remains red on this host because Git lacks `--ref-format` and the configured signing key is unavailable. Command timings use an experimental engine/CLI/module stack; cold and Rust latency effects are unmeasured. [Source, all attempts and complete evidence](NATIVE_READ_CONFIG_BEFORE_STAT.md).
