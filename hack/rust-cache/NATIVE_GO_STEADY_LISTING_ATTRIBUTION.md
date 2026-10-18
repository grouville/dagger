# Follow the remaining cost of full Go collection listing

The current controlled engine still needs roughly **35–38 seconds** for a warm, fresh-edited full listing. The [compaction screen](NATIVE_CACHE_COMPACTION_DIGEST_SETS.md) establishes no new complete-command saving. A separate capture now records both engine and CLI CPU, exact API/backend parentage and ordinary compaction activity. It returns all 4,398 ordered rows and exits successfully, with **409,567 wcprof events, none dropped or open**.

The capture uses selected Go module `7568cd0`, CLI `e7ba08d0`, engine `2014598a` and source `ff0b029a`. Every unselected optimization is off, including digest-set reuse. The CLI and source comment are fresh; the retained engine and volume are warm. Telemetry, native caching, normal GC and cleanup stay enabled. This **40.51-second profiled diagnostic is not a timing comparison**. Host CPU pressure averages 22.7%; I/O pressure averages 0.14%.

## Critical path

Every one of the **7,820 SDK API requests** has exactly one admission and one query child linked through the private HTTP transport. No temporal matching or ambiguous parent inference is used. The main query takes 38.63 seconds. Wcprof partitions its path as follows; concurrent work outside that path receives no elapsed-time credit:

| Work on the main query's path | Time |
| --- | ---: |
| Query response execution outside recorded children | 11.44 s |
| Waiting for the session lifecycle lock | 5.91 s |
| Cache publication | 4.90 s |
| Host directory imports | 3.31 s |
| Artifact item reads | 1.99 s |
| Searching existing search results | 1.70 s |

Other recorded work accounts for the rest. These are categories from one capture, not removable savings or increments to earlier measurements. The response category still needs finer attribution before choosing an implementation change.

## CPU and allocation evidence

Eight engine windows span 40.12 seconds and contain **199.53 CPU-seconds**. Background GC accounts for 46.31 cumulative CPU-seconds. The compaction recorder sees **zero calls**. An earlier pressure-heavy capture placed maintenance inside compaction while publication waited; that explains a conditional tail, rather than all ordinary listing latency.

Focused engine stacks attribute 2.62 CPU-seconds to client admission, including 2.30 in runtime initialization and 1.38 in interface reconciliation beneath result attachment. Query serving has 19.11 cumulative CPU-seconds, including 6.01 in operation preparation and 11.62 in response execution. Schema construction contributes 5.24 CPU-seconds inside preparation. These categories overlap and run concurrently; they cannot be subtracted from command time. In particular, cumulative schema CPU does not contradict the much smaller schema-getter contribution on the single critical path.

Seven complete CLI windows span 35.01 seconds and contain **21.19 CPU-seconds**. The final incomplete window ends when the CLI exits and is excluded. Full-process resource accounting reports 20.94 user and 4.67 system seconds. The samples attribute 4.10 cumulative CPU-seconds to filesync, 2.30 to pretty-frontend dispatch and 1.73 to span export into the UI database. They overlap other stack totals and do not measure wall-clock savings. The telemetry path remains active.

The allocation profile is GC-delayed and covers only part of the command's 29.94 GB allocation delta. Its 1.28 GiB flat allocation at `io.ReadAll` is almost entirely beneath `decodedSchemaCache.read`. This is a known cost: the earlier [prepared-schema experiment](NATIVE_DANG_PREPARED_SCHEMA.md) already reduces schema open/decode executions from 963 to two without establishing a useful listing improvement. A new file-identity cache would duplicate that attempted work reduction; no such cache is implemented or proposed here.

## Next experiment and review state

Follow the remaining response-execution and session-lock intervals with finer request-owned markers before changing their implementation. Existing parser, interface-field, admission and telemetry variants have component evidence but inconclusive complete-command results. They remain off; another unchanged configuration sweep would not resolve the attribution gap.

The separate [cache-usage payload-read change](NATIVE_CACHE_USAGE_PAYLOAD_READS.md) has a small clean-main patch, repeatable component gains and passing race tests. It is pushed to the fork for individual review, with no CLI-time saving claimed. The queue contains **nineteen Dagger descriptions and one Go-module description**; no new PR is opened.

The capture restores source, module configuration and feature modes. A postprocessor initially expected optional goroutine dumps that this CPU capture does not collect; the failure and corrected processor are retained, and the listing is not rerun. CPU, allocation, mutex, CLI and exact-parentage analyses all succeed.

[Full capture, exact source overlays, analyses and all diagnostic outcomes](experiments/go-steady-listing-attribution/).
