# Output publication is not the recurring bottleneck

An earlier large-workspace trace spent 1.08 seconds publishing execution outputs. Eight fresh edited checks with spans around each output, snapshot commit and lock do not reproduce that cost. All eight captures have zero dropped events and open operations.

| Phase | Median summed time per command | Largest individual operation |
| --- | ---: | ---: |
| Apply one output | 11.242 ms | 5.812 ms |
| Commit one output | 11.209 ms | 5.803 ms |
| Bind one output | 0.018 ms | 0.004 ms |
| Snapshot manager lock wait | 0.001 ms | under 0.001 ms |
| Snapshot reference lock wait | 0.001 ms | 0.001 ms |
| Snapshot metadata | 0.434 ms | 0.069 ms |

The profile covers the existing local-script Rust module (`cd6d25e`) on the selected cumulative engine. Source snapshot seeds, compact scalar restoration, per-batch telemetry metadata reuse and the selected array decoder are enabled. Telemetry stays enabled. Per-mount diagnostic spans are the only engine change in these captures. The complete profiled commands take 1.700–2.176 seconds; those are diagnostic observations, not an unprofiled speedup comparison.

Backend snapshot commits have a median summed time of 29.606 ms and a largest operation of 31.246 ms. Those counts include imports as well as compiler outputs, so they should not be added to the output-publication totals. Workspace imports usually take 174–196 ms. Discovery takes 220–249 ms, and check execution takes 989–1,146 ms.

These results move investigation toward source preparation, discovery and the compiler helper. They do not justify changing snapshot locks or durability behavior to address the original outlier. The `dang.invoke` critical-path label includes helper and engine work; it does not measure interpreter CPU alone.

The binary is `db9b4a4a52bed6d46c34e53e5c01e0b3a4bb4411f12ce765ede0f4d5b97ee410`, from source head `19eda9248` plus the recorded 37-source diagnostic overlay. Evidence and the two added span implementations are in [exec-output-phases](experiments/exec-output-phases/).
