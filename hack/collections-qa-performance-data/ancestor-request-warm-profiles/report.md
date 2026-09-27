Four local commands passed: one full check-list primer then one identical profiled check-list per variant. All four produced the exact14 rows. Original source/output/binary state was restored and the owned engine stopped. No Cloud calls.

These profiles have a fully primed catalog boundary, unlike the earlier72-call profiles collected after restart plus only a selected-test warmup. They remain diagnostic observations; their profiled CLI times are excluded from ordinary performance medians.

| Quantity | Baseline | Candidate |
| --- | ---: | ---: |
| Profiled CLI ms | 1787.86 | 1667.80 |
| Query union ms | 1580.84 | 1476.03 |
| Parent-sync count | 10.00 | 10.00 |
| Parent-sync sum ms | 147.37 | 12.89 |
| Parent-sync union ms | 114.74 | 10.49 |
| Host.directory union ms | 140.74 | 36.73 |
| Workspace.artifacts ms | 673.59 | 651.95 |
| Expansion ms | 886.02 | 800.27 |
| Git advertisement union ms | 342.90 | 330.99 |
| Go.modules ms | 373.65 | 359.26 |
| findRoots sum ms | 59.59 | 22.02 |
| Workspace.file sum ms | 54.40 | 17.04 |

Inclusive phases overlap; interval unions are not automatically critical-path savings. There is no dedicated subtree marker, so Host.directory remainder includes stat/path, subtree transfer and engine mirror/filter/hash work. go-module-details.json records temporal enclosure, not invented nested-runtime ancestry.

The same profile marker exists in both engines. These frozen binaries measure v1 on Linux; the later v2 only adds Windows protocol-root acceptance and has separate test evidence. This host has roughly6000 entries in /tmp, increasing the opportunity from removing unrelated sibling enumeration. No service-up, cold-volume, Cloud or universal500ms claim follows.
