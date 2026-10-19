Schema preparation currently creates every object/interface pairing before removing invalid ones. This candidate indexes visible field names to avoid impossible pairs, then applies the existing type, argument and recursive compatibility checks. Declared relationships and empty interfaces keep their behavior. The index and required-field snapshots live for one reconciliation pass.

Fresh-schema component benchmarks on Go 1.26.6, with construction included and four alternating pairs:

| Fixture | Before → after | Allocated bytes |
| --- | ---: | ---: |
| 128 objects / 8 interfaces | 7.18 → 1.81 ms | 12.88 → 2.19 MB |
| 512 objects / 16 interfaces | 51.99 → 8.74 ms | 98.80 → 9.13 MB |
| Dense matching, 128 / 8 | 6.68 → 4.27 ms | 11.86 → 3.22 MB |
| Already declared, 128 / 8 | 2.03 → 1.74 ms | 1.72 → 1.20 MB |
| Core-shaped, 512 / 3 | 18.92 → 17.43 ms | 19.30 → 18.17 MB |

Each listed shape improves in all four pairs. The tiny one-object/one-interface control regresses 15.88 → 17.79 µs, adding 336 bytes and two allocations. The one-interface declared control stays effectively flat. Adaptive lookups avoid copying a large field table when interfaces need only a few names; objects already implementing every interface skip index construction.

The full DagQL race suite passes. Regressions cover recursive matches, missing recursive evidence, declared relationships, empty interfaces and operation counts. The sparse regression reduces compatibility lookups 4,160 → 64 and fails on unchanged code. There is no new global cache, lock or persistent format.

This is a fork-review candidate, not ready to open upstream: complete Go and Rust command gains remain unmeasured. The retained engines are unchanged. [Every fixture, intermediate regression, source identity and result](experiments/interface-candidate-index/) is available for review.
