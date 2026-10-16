# Interface field-list snapshots: unselected experiment

A standalone candidate based on main `ff0b029a4d270a651b9a8c7286babc79089066e4` snapshots each interface's required fields once during a reconciliation pass. It shares the existing satisfaction checks and preserves the fixed-point pruning order, variance rules, views and locks. The snapshot map is lazy, temporary and local to the pass.

Six fresh-process component pairs include construction of the server and definitions:

| Definition shape | Before | After | Allocations |
| --- | ---: | ---: | ---: |
| 128 objects, 8 interfaces | 7.145 ms | 3.586 ms | 12.879 → 1.858 MB |
| 512 objects, 16 interfaces | 53.438 ms | 25.875 ms | 98.800 → 11.958 MB |

Both larger shapes improve in all six pairs. The tiny one-object/one-interface control is slower in all six pairs: 15.992 → 16.475 microseconds and 336 additional allocated bytes. Already declared relationships remain essentially flat. The first component harness omitted an installation mutex and panicked; the corrected harness and failed attempt are both retained.

These component gains do not establish faster complete commands. Four paired 64-package Rust runs measure 8.218 → 8.242 seconds, with 2/4 faster pairs and allocations 6.68 → 6.52 GB. The corresponding Go runs measure 8.517 → 8.654 seconds, with 2/4 faster pairs and allocations 4.50 → 4.37 GB. The option therefore remains off and no upstream PR is prepared for it.

The full dagql race suite passes on the standalone source. The diagnostic engine also passes eight Rust selection/correctness checks and preserves strict reuse of all six retained native-cache histories after a graceful restart. Both command arms use the same binary and module source, toggling only this option. Normal GC and telemetry stay enabled; profiling runs separately.

The running engine is `08a1f13ae88c61f3dadea8d834132d71a52d77ccf3a7d91f91ad760ef4702197`; the option is off by default. Its exact source overlays, base revision, tests, restart/retention checks and measurements are in [the archive](experiments/interface-field-snapshots/). The underlying engine dependency context is retained in the earlier [Go/Rust collection archive](experiments/rust-go-test-collections/engine/). Source snapshots are under testdata so they do not become Go packages.

A separate scalar-argument getter probe is also archived as an unselected component experiment. Its ID/JSON compatibility checks and small component gains do not establish a complete-command improvement.
