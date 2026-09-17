# Detailed Ruff filesync comparison

Validated input SHA-256: `372dd80b51425be4135ab1e6fe34746c5db13055acf885871537264d9470ac99`.

Six matched rounds, 234 profiled CLI commands, three versions. All times are milliseconds.

Main is pinned upstream 523f3fe3 plus common diagnostics and the same reserve-floor GC fix.
Both CAS versions also include the xattr opt-out and result-first writer. Only the async version
adds detached admission. This compares filesync, not Cargo or the Rust module.

Cold means a fresh engine volume and CLI state. Engine images and host OS page caches were available;
it is not a complete first installation or a cold-disk test.

## Host contention: diagnostic series

External Rust/C compilation was observed during round 5. The user canceled it and a subsequent
process check found no remaining compiler processes. The exact contention onset is not known.
All samples remain in the tables. These are not uniformly idle-host causal estimates;
small gains require a separate quiet-host confirmation. See CONTENTION.md for the retained observation.

Contention note SHA-256: `862bd2931c6aa4ff7f7c3adde54190f51aa1bbbd9bcf1cbd37baf010d84ec223`.

## Engine query elapsed time

| Flow | Main | CAS sync | CAS async | Paired async minus sync | Paired async minus main |
| --- | ---: | ---: | ---: | ---: | ---: |
| Cold import | 2228.825 | 2542.510 | 2488.054 | -32.156 | 259.298 |
| Unchanged after cold | 365.151 | 340.408 | 334.917 | -5.437 | -30.425 |
| One-file edit | 1204.558 | 832.406 | 814.587 | -13.767 | -389.961 |
| Repeat one-file edit | 363.429 | 344.154 | 335.997 | -10.840 | -29.941 |
| Move populated directory into a subdirectory | 1265.228 | 939.575 | 927.710 | -8.223 | -344.461 |
| Repeat directory move | 369.032 | 331.970 | 335.855 | 2.833 | -37.441 |
| Restore directory | 463.436 | 436.690 | 431.284 | -10.670 | -33.853 |
| Mixed: 128 edits, 64 additions, 64 deletions | 1276.488 | 846.847 | 846.646 | -1.803 | -360.269 |
| Repeat mixed diff | 371.159 | 334.210 | 341.412 | 9.255 | -25.909 |
| Restore mixed diff | 397.806 | 358.707 | 371.193 | 13.537 | -24.884 |
| Broad directory/file reorganization, additions and deletions | 1197.213 | 841.827 | 841.363 | 11.669 | -342.686 |
| Repeat broad reorganization | 371.857 | 339.884 | 366.334 | 4.232 | -16.088 |
| Restore broad reorganization | 388.527 | 368.822 | 382.755 | 12.655 | -10.018 |

## Standalone CLI elapsed time

| Flow | Main | CAS sync | CAS async | Paired async minus sync | Paired async minus main |
| --- | ---: | ---: | ---: | ---: | ---: |
| Cold import | 5374.753 | 5705.774 | 5676.602 | -49.417 | 278.297 |
| Unchanged after cold | 867.255 | 815.397 | 816.276 | 0.837 | -51.114 |
| One-file edit | 1692.246 | 1316.550 | 1342.001 | 24.693 | -351.966 |
| Repeat one-file edit | 842.274 | 865.812 | 815.954 | -50.046 | -26.477 |
| Move populated directory into a subdirectory | 1794.150 | 1442.190 | 1442.241 | 1.068 | -350.361 |
| Repeat directory move | 841.729 | 840.583 | 840.455 | 25.197 | -25.542 |
| Restore directory | 940.577 | 915.844 | 866.303 | -50.001 | -25.127 |
| Mixed: 128 edits, 64 additions, 64 deletions | 1793.966 | 1316.744 | 1317.788 | 1.056 | -402.100 |
| Repeat mixed diff | 840.949 | 865.577 | 848.747 | 7.971 | 32.886 |
| Restore mixed diff | 966.590 | 840.831 | 890.767 | 24.947 | -51.731 |
| Broad directory/file reorganization, additions and deletions | 1692.502 | 1316.164 | 1342.826 | 54.342 | -376.427 |
| Repeat broad reorganization | 866.385 | 840.439 | 866.162 | 25.355 | -49.126 |
| Restore broad reorganization | 865.940 | 865.809 | 890.719 | 25.335 | -25.564 |

Negative paired differences mean faster. Paired medians are not differences of medians.

## Range and paired direction

No outliers are removed. At n=6 nearest-rank p95 is the maximum, not a stable tail estimate.

| Flow | Metric | Main min–max | CAS sync min–max | CAS async min–max | Async faster than sync / main |
| --- | --- | ---: | ---: | ---: | ---: |
| Cold import | engine_ms | 2195.790–2643.621 | 2482.742–2624.905 | 2430.023–2533.697 | 3/6; 1/6 |
| Cold import | cli_ms | 5276.267–6233.376 | 5676.220–5928.601 | 5582.210–6027.598 | 5/6; 2/6 |
| Unchanged after cold | engine_ms | 352.338–409.638 | 330.383–348.975 | 328.020–355.636 | 4/6; 6/6 |
| Unchanged after cold | cli_ms | 816.063–1017.089 | 765.247–966.943 | 815.346–866.861 | 2/6; 4/6 |
| One-file edit | engine_ms | 1104.905–1639.203 | 812.350–844.849 | 799.788–865.118 | 5/6; 6/6 |
| One-file edit | cli_ms | 1566.568–2118.786 | 1266.016–1417.668 | 1267.106–1416.749 | 3/6; 6/6 |
| Repeat one-file edit | engine_ms | 354.591–370.668 | 335.031–355.648 | 322.192–360.390 | 5/6; 5/6 |
| Repeat one-file edit | cli_ms | 815.620–867.057 | 765.342–915.893 | 765.212–865.490 | 6/6; 4/6 |
| Move populated directory into a subdirectory | engine_ms | 1224.928–1425.557 | 917.466–993.486 | 912.130–961.187 | 4/6; 6/6 |
| Move populated directory into a subdirectory | cli_ms | 1717.585–1917.801 | 1366.504–1567.735 | 1366.604–1517.171 | 3/6; 6/6 |
| Repeat directory move | engine_ms | 359.102–389.130 | 324.355–365.305 | 321.307–350.248 | 3/6; 6/6 |
| Repeat directory move | cli_ms | 815.229–966.961 | 765.191–866.376 | 765.425–916.775 | 3/6; 4/6 |
| Restore directory | engine_ms | 439.814–506.223 | 426.760–452.868 | 419.833–850.648 | 3/6; 5/6 |
| Restore directory | cli_ms | 866.749–966.600 | 867.259–967.927 | 865.345–2325.551 | 4/6; 4/6 |
| Mixed: 128 edits, 64 additions, 64 deletions | engine_ms | 1089.778–2060.826 | 837.966–861.339 | 832.654–1977.802 | 3/6; 5/6 |
| Mixed: 128 edits, 64 additions, 64 deletions | cli_ms | 1567.438–2769.649 | 1316.256–1319.357 | 1316.490–3375.697 | 2/6; 5/6 |
| Repeat mixed diff | engine_ms | 360.059–387.348 | 324.471–383.635 | 333.059–685.177 | 1/6; 4/6 |
| Repeat mixed diff | cli_ms | 815.340–1016.787 | 765.317–965.609 | 765.313–2121.098 | 3/6; 3/6 |
| Restore mixed diff | engine_ms | 384.307–714.187 | 339.860–379.511 | 349.063–721.229 | 2/6; 5/6 |
| Restore mixed diff | cli_ms | 865.986–2121.533 | 815.349–866.245 | 815.416–2220.890 | 1/6; 5/6 |
| Broad directory/file reorganization, additions and deletions | engine_ms | 1147.596–2035.043 | 826.346–893.663 | 823.049–1575.763 | 2/6; 6/6 |
| Broad directory/file reorganization, additions and deletions | cli_ms | 1617.977–3575.552 | 1266.274–1317.541 | 1266.311–2819.884 | 2/6; 6/6 |
| Repeat broad reorganization | engine_ms | 351.046–722.496 | 333.920–384.304 | 331.517–696.293 | 2/6; 4/6 |
| Repeat broad reorganization | cli_ms | 815.264–2525.186 | 815.234–1066.953 | 767.652–1968.307 | 2/6; 5/6 |
| Restore broad reorganization | engine_ms | 385.440–415.793 | 346.097–442.958 | 368.796–823.361 | 2/6; 4/6 |
| Restore broad reorganization | cli_ms | 865.520–966.968 | 815.239–1117.513 | 815.388–1519.266 | 2/6; 4/6 |

## Observed phase durations

Per-class median elapsed unions. Nested rows overlap their parent: do not sum this table.
Zero means the operation was absent or below rounding, not missing validation.

| Flow | Phase | Main | CAS sync | CAS async |
| --- | --- | ---: | ---: | ---: |
| Cold import | Source sync, comparison and hash updates | 1372.907 | 1283.197 | 1371.678 |
| Cold import | Tree checksum | 16.229 | 16.496 | 16.793 |
| Cold import | Materialize new result (inclusive) | 754.055 | 993.165 | 1005.767 |
| Cold import |   CAS lookup (inside materialization) | 0.000 | 75.811 | 74.908 |
| Cold import |   New CAS file writes (inside materialization) | 0.000 | 651.515 | 663.354 |
| Cold import | Commit result snapshot | 55.370 | 56.754 | 58.579 |
| Cold import | Publish result metadata (inclusive) | 5.260 | 5.174 | 12.378 |
| Cold import |   Async ownership handoff (inside publication) | 0.000 | 0.000 | 7.218 |
| Cold import | Release import resources | 3.142 | 3.126 | 3.255 |
| Unchanged after cold | Source sync, comparison and hash updates | 314.475 | 290.346 | 288.604 |
| Unchanged after cold | Tree checksum | 13.580 | 14.153 | 15.105 |
| Unchanged after cold | Materialize new result (inclusive) | 0.000 | 0.000 | 0.000 |
| Unchanged after cold |   CAS lookup (inside materialization) | 0.000 | 0.000 | 0.000 |
| Unchanged after cold |   New CAS file writes (inside materialization) | 0.000 | 0.000 | 0.000 |
| Unchanged after cold | Commit result snapshot | 0.000 | 0.000 | 0.000 |
| Unchanged after cold | Publish result metadata (inclusive) | 0.000 | 0.000 | 0.000 |
| Unchanged after cold |   Async ownership handoff (inside publication) | 0.000 | 0.000 | 0.000 |
| Unchanged after cold | Release import resources | 1.962 | 1.899 | 1.925 |
| One-file edit | Source sync, comparison and hash updates | 329.195 | 291.690 | 287.942 |
| One-file edit | Tree checksum | 16.155 | 13.627 | 13.678 |
| One-file edit | Materialize new result (inclusive) | 744.685 | 433.978 | 427.859 |
| One-file edit |   CAS lookup (inside materialization) | 0.000 | 63.703 | 63.684 |
| One-file edit |   New CAS file writes (inside materialization) | 0.000 | 0.087 | 0.075 |
| One-file edit | Commit result snapshot | 52.001 | 50.422 | 49.350 |
| One-file edit | Publish result metadata (inclusive) | 5.091 | 4.470 | 4.842 |
| One-file edit |   Async ownership handoff (inside publication) | 0.000 | 0.000 | 0.187 |
| One-file edit | Release import resources | 1.884 | 1.935 | 1.928 |
| Move populated directory into a subdirectory | Source sync, comparison and hash updates | 439.638 | 408.507 | 395.376 |
| Move populated directory into a subdirectory | Tree checksum | 14.490 | 14.690 | 14.332 |
| Move populated directory into a subdirectory | Materialize new result (inclusive) | 716.162 | 433.621 | 440.461 |
| Move populated directory into a subdirectory |   CAS lookup (inside materialization) | 0.000 | 63.095 | 63.458 |
| Move populated directory into a subdirectory |   New CAS file writes (inside materialization) | 0.000 | 0.000 | 0.000 |
| Move populated directory into a subdirectory | Commit result snapshot | 50.777 | 50.573 | 49.453 |
| Move populated directory into a subdirectory | Publish result metadata (inclusive) | 5.010 | 4.547 | 4.453 |
| Move populated directory into a subdirectory |   Async ownership handoff (inside publication) | 0.000 | 0.000 | 0.000 |
| Move populated directory into a subdirectory | Release import resources | 1.989 | 1.971 | 1.965 |
| Mixed: 128 edits, 64 additions, 64 deletions | Source sync, comparison and hash updates | 351.943 | 312.171 | 312.626 |
| Mixed: 128 edits, 64 additions, 64 deletions | Tree checksum | 14.391 | 14.433 | 15.151 |
| Mixed: 128 edits, 64 additions, 64 deletions | Materialize new result (inclusive) | 804.245 | 436.266 | 436.903 |
| Mixed: 128 edits, 64 additions, 64 deletions |   CAS lookup (inside materialization) | 0.000 | 62.004 | 63.416 |
| Mixed: 128 edits, 64 additions, 64 deletions |   New CAS file writes (inside materialization) | 0.000 | 10.992 | 10.822 |
| Mixed: 128 edits, 64 additions, 64 deletions | Commit result snapshot | 50.025 | 50.118 | 49.853 |
| Mixed: 128 edits, 64 additions, 64 deletions | Publish result metadata (inclusive) | 5.063 | 4.565 | 5.364 |
| Mixed: 128 edits, 64 additions, 64 deletions |   Async ownership handoff (inside publication) | 0.000 | 0.000 | 0.303 |
| Mixed: 128 edits, 64 additions, 64 deletions | Release import resources | 1.945 | 2.012 | 2.571 |
| Broad directory/file reorganization, additions and deletions | Source sync, comparison and hash updates | 358.170 | 323.926 | 328.839 |
| Broad directory/file reorganization, additions and deletions | Tree checksum | 15.087 | 14.600 | 15.589 |
| Broad directory/file reorganization, additions and deletions | Materialize new result (inclusive) | 716.425 | 420.488 | 416.883 |
| Broad directory/file reorganization, additions and deletions |   CAS lookup (inside materialization) | 0.000 | 60.881 | 60.216 |
| Broad directory/file reorganization, additions and deletions |   New CAS file writes (inside materialization) | 0.000 | 1.924 | 1.879 |
| Broad directory/file reorganization, additions and deletions | Commit result snapshot | 51.133 | 49.032 | 49.197 |
| Broad directory/file reorganization, additions and deletions | Publish result metadata (inclusive) | 4.288 | 4.713 | 5.588 |
| Broad directory/file reorganization, additions and deletions |   Async ownership handoff (inside publication) | 0.000 | 0.000 | 0.209 |
| Broad directory/file reorganization, additions and deletions | Release import resources | 1.956 | 1.964 | 2.046 |

## Sender walk breakdown

The main source-tree walk is selected by entry count. These are wall-work counters, not CPU time.
Enumeration includes initial filesystem metadata work and scheduling. Sending includes transport
backpressure. Callback Info is not the total cost of stat. The four buckets partition each sample;
independently computed medians need not add exactly.

| Flow | Version | Entries | Walk | Enumerate/filter | Callback Info | Bookkeeping | Send stats |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Cold import | main | 12025 | 1200.194 | 203.958 | 2.574 | 10.202 | 987.643 |
| Cold import | both | 12025 | 1132.738 | 161.442 | 2.455 | 10.445 | 956.258 |
| Cold import | async | 12025 | 1206.608 | 162.308 | 2.527 | 10.126 | 1034.227 |
| Unchanged after cold | main | 12025 | 302.526 | 153.074 | 2.577 | 10.068 | 138.182 |
| Unchanged after cold | both | 12025 | 278.114 | 123.933 | 2.450 | 9.533 | 141.637 |
| Unchanged after cold | async | 12025 | 273.986 | 121.745 | 2.451 | 9.624 | 140.440 |
| One-file edit | main | 12025 | 317.667 | 160.525 | 2.652 | 10.401 | 145.871 |
| One-file edit | both | 12025 | 277.351 | 123.827 | 2.636 | 9.683 | 141.145 |
| One-file edit | async | 12025 | 274.514 | 122.506 | 2.435 | 9.692 | 140.312 |
| Move populated directory into a subdirectory | main | 12026 | 428.478 | 160.742 | 2.380 | 9.759 | 255.717 |
| Move populated directory into a subdirectory | both | 12026 | 392.031 | 128.203 | 2.602 | 9.679 | 254.328 |
| Move populated directory into a subdirectory | async | 12026 | 382.953 | 126.500 | 2.383 | 9.453 | 244.669 |
| Mixed: 128 edits, 64 additions, 64 deletions | main | 12025 | 334.885 | 161.076 | 2.571 | 10.027 | 161.227 |
| Mixed: 128 edits, 64 additions, 64 deletions | both | 12025 | 297.194 | 126.166 | 2.458 | 9.816 | 160.381 |
| Mixed: 128 edits, 64 additions, 64 deletions | async | 12025 | 293.947 | 124.738 | 2.443 | 9.670 | 156.797 |
| Broad directory/file reorganization, additions and deletions | main | 12025 | 340.453 | 160.199 | 2.638 | 10.213 | 167.977 |
| Broad directory/file reorganization, additions and deletions | both | 12025 | 304.812 | 124.470 | 2.632 | 10.066 | 165.217 |
| Broad directory/file reorganization, additions and deletions | async | 12025 | 317.290 | 130.497 | 2.620 | 9.832 | 174.509 |

## Asynchronous admission and cache readiness

Admission is optional work after immutable result creation. This is moved work, not eliminated work.
Times below include zero for runs that needed no admission; failed outcomes are listed separately.

| Flow | Runs with background work | Background duration | Remaining after query | Remaining after CLI | Failed outcomes |
| --- | ---: | ---: | ---: | ---: | --- |
| Cold import | 6/6 | 145.268 | 138.677 | 85.027 | none |
| Unchanged after cold | 0/6 | 0.000 | 0.000 | 0.000 | none |
| One-file edit | 6/6 | 0.460 | 0.000 | 0.000 | none |
| Repeat one-file edit | 0/6 | 0.000 | 0.000 | 0.000 | none |
| Move populated directory into a subdirectory | 0/6 | 0.000 | 0.000 | 0.000 | none |
| Repeat directory move | 0/6 | 0.000 | 0.000 | 0.000 | none |
| Restore directory | 0/6 | 0.000 | 0.000 | 0.000 | none |
| Mixed: 128 edits, 64 additions, 64 deletions | 6/6 | 3.331 | 0.000 | 0.000 | none |
| Repeat mixed diff | 0/6 | 0.000 | 0.000 | 0.000 | none |
| Restore mixed diff | 0/6 | 0.000 | 0.000 | 0.000 | none |
| Broad directory/file reorganization, additions and deletions | 6/6 | 0.855 | 0.000 | 0.000 | none |
| Repeat broad reorganization | 0/6 | 0.000 | 0.000 | 0.000 | none |
| Restore broad reorganization | 0/6 | 0.000 | 0.000 | 0.000 | none |

## Validity and remaining gates

- 12 complete tree readbacks, first round across all versions and four changed trees.
- Source manifests, mtimes and content-digest relations checked for every timed import; all owned fixtures restored.
- All 18 owned engines stopped after their flows. Raw evidence and volumes retained.
- Full native profiles are in runtime directories. RESULTS.json records hashes, receipt paths and summaries.
- No raw events filtered; foreground stays inside CLI timing. Only explicit admission roots can outlive it.
- Async whole-dump what-if rankings lack launch causality: independent roots remain fixed during replay.
  Baseline reconstruction passes, but those theoretical savings are not foreground speedup predictions.
- Validation/draining separates commands. Immediate-next-request overlap and sustained throughput are not measured.
- The CLI timeout wait can quantize observed completion by roughly 50 ms; tiny CLI differences are not precise wins.
- Profile-disabled confirmation, real GC/restart and writable-snapshot isolation are required before production.
- Known promotion blocker: the current immutable Mount helper creates an additional view lease without expiry.
  The expiring publisher job lease does not bound that view after a crash. See ASYNC-FOLLOWUPS.md.

No performance fix was added while this matrix was running.
