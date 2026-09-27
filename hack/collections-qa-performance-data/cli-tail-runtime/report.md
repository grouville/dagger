The 72-command local API trial passed all correctness checks, but it did not identify a general CLI shutdown winner. Three balanced rounds per measured flow are too few to infer a universal improvement. These are real local API/storage timings, not production Cloud results.

Baseline uses unchanged shutdown; queuefix backports only log worker/chunk draining fixes; overlap adds a joined early log ForceFlush before trace Shutdown. All variants use the same engine, volume and receiver.

| Flow | Baseline | Queue fix | Queue fix + overlap |
| --- | ---: | ---: | ---: |
| Core version call | 254.9 ms | 231.0 ms | 249.1 ms |
| Warm native module call | 352.9 ms | 362.9 ms | 353.5 ms |
| New input → native module call | 375.1 ms | 361.6 ms | 335.6 ms |
| Greetings check -l --all | 1674.6 ms | 1669.8 ms | 1669.0 ms |
| New input → native generate | 453.2 ms | 432.5 ms | 446.2 ms |

Values are median full CLI exit times. The paired per-round differences and all 72 numeric samples are preserved separately; improvements in one flow do not establish a winner for the others.


| Median paired change vs baseline | Queue fix | Queue fix + overlap |
| --- | ---: | ---: |
| Core version call | -3.6 ms | +7.9 ms |
| Warm native module call | +9.9 ms | +16.3 ms |
| New input → native module call | -28.6 ms | -7.3 ms |
| Greetings check -l --all | -4.8 ms | +1.2 ms |
| New input → native generate | -31.6 ms | -44.1 ms |

Negative means faster within the same balanced round. For example, the fresh-module overlap difference of marginal medians is 39.5 ms, but the median paired improvement is 7.3 ms; the three paired changes are −7.3, −3.0 and −149.2 ms. The small sample and outlier make a broad speedup claim unwarranted.

The baseline CLI itself used median 170.9 ms of user+system CPU for the core call and 543.5 ms for the expanded check listing. That is a concrete next profiling target. CPU time can overlap engine/network work and is not a removable wall-time estimate.

Correctness covered 24 primer/smoke calls, 45 measured calls and 3 expected failing checks. Listings matched known identities and the reference output; module calls returned exact input bytes; generation produced exact bytes; the sentinel failed for every variant. Eighteen fresh inputs were distinct, and the original primed input/generated-file state was restored before every ordinary module comparison. Fixtures, original engine binary and network attachment were restored; the API/stores and engine were stopped. No resources were deleted and no production Cloud calls were made.

The first setup attempt launched zero CLI commands. It failed because the empty receiver record list arrived as JSON null. Its failure and successful cleanup remain archived; version 2 handles that initial empty state.

This run used a retained engine/cache, an empty CLI config and DO_NOT_TRACK=1. It excluded setup, counter snapshots and receiver quiet observation from command wall timing, and used no profiler or artificial delay. Workspace/artifact/generator navigation was smoke coverage; native generate is not SDK code generation. Receiver acceptance was checked for every command, but the run is not a proof of durable background delivery.
