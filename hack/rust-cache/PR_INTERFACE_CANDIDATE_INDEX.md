Schema preparation compares every object with every interface, then repeatedly removes incompatible matches. This change indexes visible field names to avoid impossible pairs before applying the existing type, argument and recursive checks. Declared relationships and empty interfaces keep their behavior. The index lasts for one reconciliation pass.

On the experimental development stack, complete Go test listing on dagger/dagger after a test edit improves **8.56 → 8.27 seconds median**, faster in all four alternating pairs. Allocation falls **9.99 → 9.58 GB**. Ordinary-source edits are effectively flat at **5.46 → 5.40 seconds**. Both modes use the same engine binary, CLI and Go module; only interface matching changes. Each command starts a fresh CLI on a warm engine and includes normal telemetry and session cleanup. All 24 commands return correct rows and exit successfully. Cold performance is unmeasured.

The normal getters still execute: profiles in both modes retain 800 getter executions and 799 unchanged test-discovery hits. Eighteen Go checks and 28 Rust cases exercise discovery, selection, real execution, expected failures, restored source and native compilation-cache reuse. This does not establish a Rust latency improvement.

Fresh-schema component benchmarks on Go 1.26.6, with construction included and four alternating pairs:

| Fixture | Before → after | Allocated bytes |
| --- | ---: | ---: |
| 128 objects / 8 interfaces | 7.18 → 1.81 ms | 12.88 → 2.19 MB |
| 512 objects / 16 interfaces | 51.99 → 8.74 ms | 98.80 → 9.13 MB |
| Dense matching, 128 / 8 | 6.68 → 4.27 ms | 11.86 → 3.22 MB |
| Already declared, 128 / 8 | 2.03 → 1.74 ms | 1.72 → 1.20 MB |
| Core-shaped, 512 / 3 | 18.92 → 17.43 ms | 19.30 → 18.17 MB |

Each listed shape improves in all four pairs. The tiny one-object/one-interface control regresses 15.88 → 17.79 µs, adding 336 bytes and two allocations. The one-interface declared control stays effectively flat. Adaptive lookups avoid copying a large field table when interfaces need only a few names; objects already implementing every interface skip index construction.

Full DagQL race suites pass on the standalone patch and its engine port; the port also passes the Dang SDK race suite. Regressions cover recursive matches, missing recursive evidence, declared relationships, empty interfaces and bounded compatibility lookups. The sparse regression reduces compatibility lookups 4,160 → 64 and fails on unchanged code. Index construction still reads metadata, included in the benchmarks. The change adds no global cache, lock or persistent format.

The [standalone branch](https://github.com/grouville/dagger/tree/experiment/interface-candidate-index) is based on `ff0b029a4d270a651b9a8c7286babc79089066e4`. This description is prepared for fork review; no PR is open. [Component evidence](experiments/interface-candidate-index/) and [complete-command evidence, exact build inputs and checks](experiments/interface-candidate-index-engine/) retain all attempts and the controls that exposed earlier regressions.
