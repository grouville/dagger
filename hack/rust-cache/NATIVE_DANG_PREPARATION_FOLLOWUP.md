# Reduce repeated Dang preparation during Go discovery

The full Go listing still spends substantial CPU preparing hundreds of module invocations after the metadata I/O stall ends. Two isolated prototypes remove work from this preparation. Neither has been installed in the running engine, and neither has a measured complete-command gain yet.

## Fill the final syntax directly

The selected parser cache currently allocates temporary reflected structs and interface values, copies them into the final syntax tree, and discards the temporaries. The prototype fills newly allocated destination fields directly. Each invocation still receives independent syntax, source locations, clients and evaluation state.

Four comparisons in alternating orders use the actual module sources and 64 mount paths. The syntax cache is warm, but every operation creates fresh syntax. This work occurs when an application edit requires a module invocation; it is unrelated to replaying an unchanged compiled application.

| Module source | Preparation before → after | Allocated bytes before → after |
| --- | ---: | ---: |
| Go | 4.52 → 3.33 ms | 1,327,192 → 702,800 |
| Gomod | 3.03 → 2.41 ms | 881,520 → 470,264 |
| Rust | 3.30 → 2.26 ms | 895,960 → 476,760 |

The focused race suite passes, covering independent syntax, concurrent evaluation, cache eviction, edits, diagnostics, relative imports and current clients. This improves an existing private parser-cache prototype; it is not a standalone change against unmodified Dang.

## Skip API values that are immediately discarded

`populateSchemaFunctions` constructs function signatures and argument records for fields on every schema type, although this loop exports only fields on `Query`. Receiver methods use their own lookup path, and mutation values are constructed separately. Moving the existing query-type condition before construction avoids the discarded work.

Four alternating comparisons use introspection captured from the running engine:

| Preparation | Time before → after | Allocated bytes before → after |
| --- | ---: | ---: |
| API values only | 0.614 → 0.201 ms | 381,284 → 140,440 |
| Complete type and value scopes | 2.06 → 1.67 ms | 1,526,086 → 1,285,176 |

The complete scope measurement improves by about 19%; the values-only measurement is not an estimate of the whole invocation's speedup. The focused schema/import race suite passes. This small guard can be evaluated independently of the parser-cache work.

The first benchmark input, a checked-in SDL fixture, failed schema validation before timing. That failed attempt is retained and excluded. The successful measurements use the engine's actual introspection JSON.
