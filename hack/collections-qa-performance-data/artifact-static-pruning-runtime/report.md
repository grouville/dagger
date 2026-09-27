# Targeted artifact metadata pruning: 38 local commands

The candidate removes static schema/tree work from targeted artifact resolution. The intended operation reduction is proven, while the small ordinary timing sample is mixed. It is not a general warm-listing improvement yet.

| Ordinary flow | Samples per arm | Baseline median | Candidate median | Aligned differences, candidate minus baseline |
| --- | ---: | ---: | ---: | --- |
| Warm `check -l --all` | 4 | 1360.8 ms | 1390.3 ms | 17.5, -50.2, 35.6, 30.0 ms |
| Warm `list -a` | 2 | 1377.0 ms | 1320.0 ms | -86.4, -27.6 ms |
| New app comment → `check -l --all` | 4 | 1483.4 ms | 1356.4 ms | -208.3, -62.3, -282.8, -53.6 ms |

The four engine blocks ran baseline/candidate/candidate/baseline. Each block primed both exact listing commands before ordinary samples. Aligned samples are correlated block observations, not independently randomized pairs. Comment contents were unique and first-seen in each arm, then restored. They test real input invalidation, not fresh-volume cold. The selected native test-body edits and generator-listing controls are correctness/setup rows, excluded from these medians.

All ordinary values are retained in `runtime-numeric.json`:
- warm checks: baseline [1403.8, 1350.5, 1344.0, 1371.0] ms; candidate [1421.3, 1300.3, 1379.7, 1401.0] ms.
- warm artifacts: baseline [1361.0, 1393.1] ms; candidate [1274.6, 1365.5] ms.
- fresh-edit checks: baseline [1500.3, 1466.5, 1638.9, 1410.2] ms; candidate [1292.0, 1404.2, 1356.2, 1356.6] ms.

## Mechanism confirmed by separate profiles

Each variant was restarted, fully primed with the exact `check -l --all`, and then profiled separately. Those instrumented durations are excluded from ordinary timing. Both profiles have zero open operations and zero dropped events.

| Within each repeated Address.container | Baseline | Candidate |
| --- | ---: | ---: |
| Query.typeDef calls | 195 | 18 |
| TypeDef.withOptional calls | 273 | 33 |
| Three overlapping Address calls | 31.62 / 27.89 / 31.30 ms | 8.99 / 7.62 / 9.11 ms |
| Whole-command recorded operations | 20,042 | 17,610 |

The three repeated lookups overlap, so their durations must not be added. Their maximum shrank about 22.5 ms in this diagnostic pair. The first Address also narrowed its metadata calls (196→19 TypeDef requests and 273→33 optionality requests). Its total duration changed 313.14→291.17 ms while its two authored backend calls remained about 103 ms and 158 ms.

Four Address occurrences remain. The backend constructor and `goTestBase` still execute once each, followed by three cache hits each; `Go.modules` still executes once, and the three module test-discovery functions still execute. No receiver, dynamic input, NEVER/PER_CALL call occurrence, or authored function was reused or suppressed by the pruning. The removed TypeDef requests were already cache hits: their identity/query/selection overhead still existed and is now avoided.

The full catalog was 652.28→664.66 ms and expansion was 926.58→857.23 ms in the profile pair. Go.modules and other nested durations also changed, so the complete 69.35 ms expansion difference is not attributable solely to this patch. Inclusive phase totals overlap; profiles locate the mechanism rather than predict whole-command gain.

## Scope and correctness

38/38 local commands met their expected outcomes. Both variants produced the exact ordered 14 check rows, the same ordered artifact listing and generator listing, and the expected core version. Each ran the selected `TestFormatResponse` after a distinct real `t.Log` body edit; the command required the exact selected artifact identity plus one passing check. Those two correctness/setup rows took 16.30 s and 10.65 s and are not a performance comparison. No Cloud calls, fresh-volume cold runs, service-up runs, or SDK code-generation timing occurred.

The temporary task-owned engine was removed; original engine and heavy init were untouched and left stopped; the retained volume was preserved; all source and generated fixture bytes were restored. Measured-command engine writes totalled 2,789,376 bytes; that counter excludes startup/shutdown and gaps.

Both engines were rebuilt together from the frozen ec6 behavior stack. Common overlays restore all post-0d production deltas, including attachables extraction and managed-start changes. Both use the same normal heavy init, d685 CLI, six SDK blobs, image, retained volume and local transport. Only candidate `core/schema/artifacts.go` differs. VCS build metadata is 2088d5ef; effective source overrides are pinned explicitly in the recipe, not inferred from that version string. No split init, new socket connector, SDK migration, phase scheduler, or held telemetry prototype is included.

## Adoption boundary

The normal/race selector gates passed before this run. Literal known-module filtering retains entrypoints, aliases and promotion collisions; wildcard, escaped, malformed and unknown prefixes retain full traversal. Loading/config/SDK inventory and the final complete matcher remain unchanged. Unfiltered catalog discovery still builds every relevant tree.

This is worth keeping as a small work-elimination candidate, not selling as a demonstrated broad warm speedup: the ordinary warm check median was 29.6 ms higher. The source error-surface caveat remains: an unrelated already-served malformed module whose failure occurs only during artifact-tree construction would no longer be constructed for an exact different-module lookup. This can align warm behavior with already-narrowed loading, but should be an explicit product/correctness decision before adoption. No further runtime confirmation was launched.
