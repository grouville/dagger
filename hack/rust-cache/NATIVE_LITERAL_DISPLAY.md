# Format composite literals without repeated copies

List and object display on main appends every element to an immutable string. Each append copies the prefix already built. Long lists therefore take quadratic work; this path is used when displaying arguments and logging results. It appeared while investigating the grouped hash request's remaining time outside its resolver.

The [standalone change](https://github.com/grouville/dagger/commit/5846720ef) uses `strings.Builder` for both composites and returns the two empty forms directly. Element order, punctuation, escaping and complete text are preserved. No telemetry data is omitted. The branch starts at main `5d313bf2e` and is independent of the Rust cache and grouped-hash API.

## Component measurements

The benchmark formats lists and objects containing 1,024 digest-sized strings. Three runs use ten iterations each; medians are shown below.

| Composite | Main | Builder | Main allocation | Builder allocation |
| --- | ---: | ---: | ---: | ---: |
| List | 14.73 ms | 0.544 ms | 83.6 MB | 0.581 MB |
| Object | 19.57 ms | 0.556 ms | 96.5 MB | 0.579 MB |

The list's main allocation grows from 21.1 MB at 512 elements to 83.6 MB at 1,024. The builder's allocation grows from 0.253 MB to 0.581 MB. These establish a component improvement; no complete Rust command gain is assigned to this change yet. It must not be added to the grouped-hash medians.

Golden cases preserve empty values, nested composites, non-sorted field order, numbers, booleans, Unicode, quotes, backslashes and newlines. They pass before and after. The complete `dagql/call` package passes under race detection, including existing ID display, binary redaction, serialization and identity tests.

The [data](experiments/literal-display/measurements.json) and raw samples retain all sizes and runs. The change is pushed to Guillaume's fork; no PR is open.

## Complete edited commands

The formatter was then installed in the experimental engine. Both engines contain the same grouped-hash API, primitive ownership optimization, content-key syntax cache and disabled lease-phase diagnostics. Both use Rust module `28dab90`. The formatter is the only difference. Every measured command edits a used Rust value, starts a fresh CLI and keeps telemetry enabled; wcprof is off. Two preparation rounds precede eight rotating pairs per scenario. A second series swaps engine binaries while preserving each engine's cache volume and source history. All shutdowns exit zero.

| Edited command | First series, control → formatter | Crossover, control → formatter | Crossover paired saving |
| --- | ---: | ---: | ---: |
| 130-crate leaf | 0.695 → 0.698 s | 0.682 → 0.698 s | −11.6 ms, 2/8 faster |
| 130-crate shared dependency | 1.437 → 1.384 s | 1.369 → 1.362 s | 4.0 ms, 4/8 faster |
| 1,026-crate leaf | 2.218 → 2.375 s | 2.231 → 2.286 s | 1.4 ms, 4/8 faster |
| Actual small collection tests | 1.049 → 1.023 s | 1.036 → 1.023 s | 15.9 ms, 6/8 faster |

These results do not establish a reliable complete-command improvement from formatting alone. The first series includes substantial I/O pressure and multi-second tails, including slower Cargo runs. All observations are retained. The component improvement is real, but it must not be described as a comparable command-level saving. Both engines retain 130/130, 1,026/1,026 and 6/6 compiled results, with the expected preceding edit batches of 130, two and four actions.

Four fresh large-leaf captures per engine then combine wcprof with CPU profiles and before/after allocation profiles, separately from timing samples. Every capture is complete, both CPU windows cover every command, and host I/O stalls stay below 6.3%. The formatter engine still allocates about 1.59 GiB in `ResultCallLiteral.cloneWith`; allocation stacks lead to `defaultPersistedSelfCodec.EncodeResult`, through `Array[String].NthValue`, while capturing cache evidence. This identifies another copy of the full producer arguments per list item. The [primitive-array persistence follow-up](NATIVE_PRIMITIVE_ARRAY_CODEC.md) isolates that cost without suppressing telemetry.

The command samples, pressure counters, engine restart records, cache verifications, profile summaries and reproduction drivers are archived in [the command follow-up](experiments/literal-display-command/measurements.json). Raw profiling files remain in the recorded local capture directory.
