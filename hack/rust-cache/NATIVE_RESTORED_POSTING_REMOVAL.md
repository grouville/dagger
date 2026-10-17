The full Go listing investigation exposed a 158.19-second automatic DagQL metadata prune. It removed 79,517 persisted roots from a graph of 918,097 results. Snapshot collection occupied the final 3.32 seconds. The prune overlapped the last 10.6 seconds of one listing and then prevented the next benchmark command from passing its idle-admission check. That command never started. The interrupted Go workspace-path experiment retains every observation and remains unselected.

The restored digest index still removed each result by visiting every digest in its output class. With D aliases and R imported results, deleting the group therefore performed D × R map operations, even though the aliases already shared one membership map. A CPU profile of the focused reproduction places 98.3% of samples under this deletion loop. The large equivalent groups are real: the previous Go discovery database contained a class with 19,456 results and 19,457 digests.

The candidate records which original imported groups contain each result. Collection removes the result from each shared membership once. When a group becomes empty, it visits the group's original digest/posting pairs once and removes empty aliases. Later digest-specific additions survive. Keeping original membership and posting identities preserves the existing behavior across class merges, compaction and subsequent additions. Runtime exact postings, ownership, persistence, cache keys, eviction policy and the existing graph lock keep their behavior. There is no new lock.

Three samples per arm use fresh cache objects and a warm filesystem cache. Fixture construction and persistence/import are outside the prune interval. The complete prune benchmark includes compaction, root selection, ownership release and graph deletion; it checks the resulting population and pressure estimate. The fixture has independent persisted roots and no snapshot manager, so this is a DagQL prune measurement, not containerd cleanup or a full CLI command.

| Fixture | Before median | Candidate median |
| --- | ---: | ---: |
| Complete prune, 513 roots removed | 16.22 ms | 3.42 ms |
| Complete prune, 2,049 roots removed | 274.84 ms | 10.72 ms |
| Complete prune, 8,192 roots removed | 5.122 s | 46.06 ms |
| Digest-index removal, 4,096 results × 4,096 aliases | 961.16 ms | 1.10 ms |

The complete largest prune allocates approximately 16.01 MB in both arms. Index removal itself allocates nothing. This changes imported deletion from quadratic work to work proportional to original memberships plus aliases, in addition to the existing runtime-exact postings.

The reverse index has a cost at restore. For one group of 4,096 results/aliases, construction allocates 0.946 → 1.405 MB and takes 1.77 → 2.99 ms. For 4,096 independent one-result groups, allocation is 1.585 → 2.175 MB and time is 1.93 → 5.42 ms. These are index-construction measurements, not complete database-import measurements or process retained heap. The candidate intentionally exchanges linear bookkeeping for avoiding repeated deletion of the same membership.

The isolated patch applies on top of the shared-postings proposal, revision `8d84808e98c63844ec356c15a8406e933f02e1bd`, based on upstream `ff0b029a4d270a651b9a8c7286babc79089066e4`. Its full DagQL race suite passes in 66.821 seconds. New cases exercise collection after a class merge while preserving a later exact posting, and one imported result belonging to multiple original groups. Existing cases cover imported/exact removal, expiry, resource compatibility, ownership cascades, forced compaction, reset, persistence and protected roots.

Two early benchmark assertions were corrected before the reported measurements: compaction can resolve pressure without pruning, and the coarse planner need not reach a one-byte target exactly. Both rejected logs are retained. Final validation checks the actual best-effort contract, the collected population and the number of removed roots; every reported sample succeeds.

The diagnostic engine replaces the old binary through a graceful exit 0 on the same volume. The old binary takes 177.85 seconds to save and stop; this is setup, not a before/after shutdown comparison. All six native Rust histories retain their 130/130, 1,026/1,026 and 6/6 cached actions after restart. The controlled engine's enabled and disabled branches also pass focused race checks.

The full listing comparison uses the same binary, CLI and selected Go module in both modes, fresh source edits and a fresh CLI per invocation, with normal telemetry and GC. Both modes build the reverse index at import; the switch controls deletion only. The restore-cost measurements above are therefore separate from this full-command comparison.

| Measured pair | Original deletion | Candidate deletion |
| --- | ---: | ---: |
| 1, candidate first | 48.53 s | 48.98 s |
| 2, original first | 46.42 s | 48.35 s |
| Median | 47.47 s | 48.66 s |

Every measured command returns identical 4,398 rows and exits 0. The excluded initialization pair adds a real test, returns the correct 4,399 rows, and completes in 49.35 → 43.99 seconds. There is no ordinary-listing improvement: neither measured pair is faster, engine CPU medians are 232.39 → 242.32 seconds, and allocation is 37.16 → 37.47 GB. Measured host I/O pressure stays below 0.34%; initialization reaches about 5.9%.

No metadata prune occurs in the full-command cohort: the estimate grows from 3.162 to 3.493 GB, below the unchanged 4.295 GB maximum. The results therefore establish no full-command pruning benefit. The diagnostic deletion switch is restored off. The additional reverse index remains common to both modes in this diagnostic binary; the candidate is isolated for maintenance experiments and is not selected as an ordinary-listing latency improvement.

The reproduction identifies a quadratic component of the observed maintenance pause. It does not attribute all 158 seconds to that component. The next hot-path investigation must address the listing's remaining execution and telemetry cost using the existing CLI/engine profiles.

[Reproduction and behavior checks](https://github.com/grouville/dagger/commit/a7917238abbfddc2227ded3641c9a858f6dea807), [production fix](https://github.com/grouville/dagger/commit/52125b89732b29749748b7a81796fd911a3eb33c), [draft review description](PR_ENGINE_REMOVE_RESTORED_POSTINGS.md), and [archived evidence](experiments/restored-postings-removal/). No PR is open.
