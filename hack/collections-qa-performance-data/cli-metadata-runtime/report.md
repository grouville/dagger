# Bulk CLI metadata: ordinary command measurements

One engine served both matched CLIs; only the metadata query path differed. All32 benchmark and primer commands returned expected output. No profiler or diagnostic hooks were enabled.

| Flow | Old query | JSON snapshot | Repetitions |
| --- | ---: | ---: | ---: |
| Local warm core | 377.1 ms | 226.6 ms | 3 pairs |
| Local warm module | 443.1 ms | 304.2 ms | 3 pairs |
| Local fresh input module | 450.1 ms | 341.9 ms | 1 pairs |
| Cloud warm core | 628.1 ms | 591.5 ms | 3 pairs |
| Cloud warm module | 823.3 ms | 817.2 ms | 3 pairs |

Local warm medians improved by150.5ms for the core call and138.9ms for the native module call. Normal Cloud runs improved by36.6ms and6.1ms respectively in this small sample. The local improvement does not establish an equivalent Cloud improvement. Both modes still need separate end-to-end evaluation. The single edited-input pair ran baseline first on a shared engine; treat it as an invalidation check, not an independent first-run timing comparison.

The added collection parser probe then failed on the old-query CLI with a missing `[GoModule]` TypeDef. The candidate probe was not run because the driver stops on failure. This is a correctness gate, not a timing sample; classification against the unchanged engine is pending.

The driver restored input files and the original engine binary, stopped its owned engine, retained its volume and deleted no resources. It attempted14 Cloud and19 local commands. Raw outputs, telemetry profiles and engine binaries are excluded from this bundle.

This is a response representation optimization. It preserves authoritative schema/view metadata and reduces thousands of getter results; it does not remove initial SDK or core TypeDef construction. The broader500ms target is not achieved for all flows.
