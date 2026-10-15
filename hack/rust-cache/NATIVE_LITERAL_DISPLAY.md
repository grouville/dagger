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

The [data](experiments/literal-display/measurements.json) and raw samples retain all sizes and runs. The change is pushed to Guillaume's fork; no PR is open. Applying it to the experimental engine and measuring full commands remains a separate step.
