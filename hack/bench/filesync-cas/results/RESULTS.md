# Ruff filesync: main / synchronous CAS / asynchronous CAS

Status: complete-validated-n6

Medians in milliseconds. The delta is the median of matched differences, not a subtraction of medians.

| Flow | Metric | Main | CAS sync | CAS async | Async − sync | Async − main |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Cold import | engine_ms | 2228.825 | 2542.510 | 2488.054 | -32.156 | 259.298 |
| Cold import | cli_ms | 5374.753 | 5705.774 | 5676.602 | -49.417 | 278.297 |
| Unchanged after cold | engine_ms | 365.151 | 340.408 | 334.917 | -5.437 | -30.425 |
| Unchanged after cold | cli_ms | 867.255 | 815.397 | 816.276 | 0.837 | -51.114 |
| App edit | engine_ms | 1204.558 | 832.406 | 814.587 | -13.767 | -389.961 |
| App edit | cli_ms | 1692.246 | 1316.550 | 1342.001 | 24.693 | -351.966 |
| Unchanged after app edit | engine_ms | 363.429 | 344.154 | 335.997 | -10.840 | -29.941 |
| Unchanged after app edit | cli_ms | 842.274 | 865.812 | 815.954 | -50.046 | -26.477 |
| Directory move, app edit retained | engine_ms | 1265.228 | 939.575 | 927.710 | -8.223 | -344.461 |
| Directory move, app edit retained | cli_ms | 1794.150 | 1442.190 | 1442.241 | 1.068 | -350.361 |
| Unchanged after move | engine_ms | 369.032 | 331.970 | 335.855 | 2.833 | -37.441 |
| Unchanged after move | cli_ms | 841.729 | 840.583 | 840.455 | 25.197 | -25.542 |
| Restore directory, app edit retained | engine_ms | 463.436 | 436.690 | 431.284 | -10.670 | -33.853 |
| Restore directory, app edit retained | cli_ms | 940.577 | 915.844 | 866.303 | -50.001 | -25.127 |
| Mixed content diff: 128 edits, 64 adds, 64 deletes | engine_ms | 1276.488 | 846.847 | 846.646 | -1.803 | -360.269 |
| Mixed content diff: 128 edits, 64 adds, 64 deletes | cli_ms | 1793.966 | 1316.744 | 1317.788 | 1.056 | -402.100 |
| Repeat mixed content diff | engine_ms | 371.159 | 334.210 | 341.412 | 9.255 | -25.909 |
| Repeat mixed content diff | cli_ms | 840.949 | 865.577 | 848.747 | 7.971 | 32.886 |
| Restore mixed content diff | engine_ms | 397.806 | 358.707 | 371.193 | 13.537 | -24.884 |
| Restore mixed content diff | cli_ms | 966.590 | 840.831 | 890.767 | 24.947 | -51.731 |
| Broad directory/file reorganization + adds/deletes | engine_ms | 1197.213 | 841.827 | 841.363 | 11.669 | -342.686 |
| Broad directory/file reorganization + adds/deletes | cli_ms | 1692.502 | 1316.164 | 1342.826 | 54.342 | -376.427 |
| Repeat broad reorganization | engine_ms | 371.857 | 339.884 | 366.334 | 4.232 | -16.088 |
| Repeat broad reorganization | cli_ms | 866.385 | 840.439 | 866.162 | 25.355 | -49.126 |
| Restore broad reorganization | engine_ms | 388.527 | 368.822 | 382.755 | 12.655 | -10.018 |
| Restore broad reorganization | cli_ms | 865.940 | 865.809 | 890.719 | 25.335 | -25.564 |

- Six cyclic rounds over three arms: every arm occupies every position twice.
- First round, all three arms, edited/moved/mixed/reorganized trees; validation-separated imports, not retained snapshot-ID readback or immediate-overlap stress.
- Foreground stays CLI-bounded; only explicit independent admission roots may extend up to 10s beyond CLI; all events retained.
- Profiled diagnostic only; native Cargo is not part of this filesync matrix.
- Main means pinned 523f3fe3 plus common diagnostics and the same reserve-floor GC fix.
- n=6 p95 equals the maximum; all outliers and pressure measurements retained.
- Background failures remain diagnostic samples; consult admission outcomes, not just latency.
- Profile draining/validation separates imports; immediate-next-request busy/miss behavior and sustained throughput remain untested.

Full profiles, admission tails, phase timing, failures and pressure are retained in RESULTS.json.
