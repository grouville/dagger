The low-width follow-up completed12/12 exact-output local commands: four explicit primers, six ordinary warm listings and two separately primed profiles. The original public fixture and engine were restored, and the new owned copy was removed. No Cloud call ran.

The same exact public source/config/lock bytes were copied under the repository’s ignored bin directory, with a new Git boundary and public origin. Both variants used that one path. Parent widths are recorded in provenance.json; unlike the earlier /tmp path, this path does not traverse the roughly6000-entry /tmp directory. Git commit identity is new and setup is excluded.

There are only three ordinary samples per variant, in fixed baseline-then-candidate blocks. This checks representativeness at a different parent width; it does not isolate host noise or establish stable percentiles.

| Warm check-l | Samples (s) | Median (s) |
| --- | --- | ---: |
| baseline | 1.670 / 1.405 / 1.447 | 1.447 |
| candidate | 1.740 / 1.443 / 1.433 | 1.443 |

Median change: -3.4ms (-0.2%). This does not establish a whole-command speedup on the lower-width path. The roughly95ms median benefit measured on the earlier /tmp path must not be generalized to ordinary narrow directories. The algorithm removes sibling-width-dependent work; its practical gain depends on that width.

| Separate profile quantity | Baseline | Candidate |
| --- | ---: | ---: |
| Profiled CLI ms | 1399.56 | 1443.12 |
| Query union ms | 1198.22 | 1230.31 |
| Parent-sync count | 10.00 | 10.00 |
| Parent-sync sum ms | 14.14 | 9.05 |
| Parent-sync union ms | 10.82 | 6.69 |
| Host.directory union ms | 35.47 | 31.34 |

The profiles follow a full identical listing primer and are excluded from ordinary medians. Inclusive intervals overlap; even interval union is not an exact critical-path prediction. Remaining Host.directory includes stat/path resolution, actual subtree sync and mirror/hash work.

Frozen v1 Linux binaries were measured; separate v2 portability tests are not a second binary measurement. No fresh-volume cold, service-up, Cloud or universal500ms claim follows.
