The largest measured cold image layer is the bundled Go toolchain, not the compiler-cache seed. Joining verified OCI manifest digests to the two saved cold profiles gives 2.577 / 2.711 s applying its 63.8 MB compressed layer. The module-cache and build-cache layers take 0.418 / 0.414 s and 0.793 / 0.802 s respectively. These are instrumented layer intervals, not newly benchmarked command timings or additive forecasts.

The manifest and configuration were copied read-only from the exact stopped benchmark engine and checked against their content digests. The Go image declares version 1.26.8. Its toolchain layer was copied and verified, then enumerated as a tar stream without extracting files or starting the engine. Existing engine state and volumes were untouched; no Cloud or registry requests occurred.

| Toolchain subtree | Entries | Regular files | Uncompressed file bytes |
| --- | ---: | ---: | ---: |
| `src` | 12,802 | 11,478 | 127,562,029 |
| `test` | 3,773 | 3,454 | 7,748,977 |
| `pkg` | 17 | 13 | 67,449,661 |
| `bin` | 3 | 2 | 18,545,430 |
| `api` | 30 | 29 | 8,982,743 |

There are 16,705 entries in the layer, including 4,061 regular files inside `src/**/testdata/` and 1,753 `src/**/*_test.go` files. These classifications overlap; they must not be summed into a unique deletion count. The distribution's top-level `test` tree represents about 23% of entries but only 7.7 MB. This identifies filesystem metadata work that compressed-byte measurements alone obscure. It does not prove that all those entries are unnecessary for every supported SDK workload.

The next packaging experiment should distinguish a compiler/runtime payload from Go distribution maintenance fixtures, retaining every file required by supported generation, compilation, cgo, race/coverage, linking and debugging flows. An OCI deletion layer alone would still extract its parent first: reducing initial hydration requires changing the packaged filesystem/layer layout. Any reduced payload must have an explicit compatibility contract and actual checks; no category has been deleted by this audit. The SDK static-metadata work may avoid needing the entire toolchain for listing, while execution still benefits from reducing required hydration.

Enumeration, copy and compressed-digest verification took 0.91 s together on this warm host. That is a different operation from containerd application: no file creation, ownership, permissions, whiteouts or timestamp restoration. It is not an optimized replacement for the 2.7 s apply interval and must not be subtracted from it as a measured saving.

`go-layer-timing.json` contains the exact layer matches in each existing profile, and `toolchain-population.json` contains only fixed-category counts. Raw image configuration and the compressed payload remain private under `/tmp`. `count-layer.py` records the bounded read-only enumeration.
