The saved profiles rule out new TCP/TLS setup and local ref parsing as meaningful Git bottlenecks in this fixture. All seven requests in each profile reused existing HTTP connections. The dominant measured interval is request-write to first response byte, which includes network and server response waiting; it does not identify server CPU.

Each profile follows an identical complete check-list primer. Unix was profiled first, Docker second, using the same diagnostic engine/volume and restored public fixture. These two profiles are attribution observations, excluded from ordinary latency medians. Both have zero open operations, zero dropped events, zero error outcomes in these phases and zero write-pairing ambiguity events.

| Fixed-label measurement | Unix profile | Docker profile |
| --- | ---: | ---: |
| Git advertisements / successful writes / first-byte events | 7 / 7 / 7 | 7 / 7 / 7 |
| Reused / new connections | 7 / 0 | 7 / 0 |
| DNS / TCP connect / TLS events | 0 / 0 / 0 | 0 / 0 / 0 |
| Connection acquisition, sum | 0.007 ms | 0.008 ms |
| Complete advertisement, union | 385.63 ms | 384.95 ms |
| Write to first byte, union | 385.39 ms | 384.74 ms |
| Write to first byte, sum | 857.45 ms | 950.63 ms |
| Last first byte through parsed return, sum | 1.937 ms | 1.189 ms |
| AllReferences validation, sum | 0.199 ms | 0.237 ms |
| Ref conversion and sorting, sum | 0.178 ms | 0.163 ms |
| Source context loads, count | 14 | 14 |
| Source context loads, union | 10.49 ms | 10.72 ms |
| Longest SDK load | 124.36 ms | 121.60 ms |
| Context immediately before that SDK load | 6.15 ms | 8.11 ms |
| Runtime process inside that SDK load | 95.73 ms | 93.74 ms |
| Catalog | 589.20 ms | 620.76 ms |
| Collection expansion | 551.05 ms | 563.86 ms |

Nested sums overlap and cannot be added as potential command savings. The post-first-byte interval includes remaining headers, body transfer, decoding and return handling. These profiles do not measure response byte counts. A smaller ref advertisement may reduce remote enumeration work, but these data cannot establish that the server enumerates refs on the critical path or that another protocol exchange preserves anonymous-access semantics.

The SDK/context-overlap proposal is low priority for this fixture: the only expensive SDK load is preceded by just 6–8 ms of context work; the other thirteen SDK loads are each under 0.06 ms. Moving SDK loading earlier would not remove its roughly 94–96 ms registration process. The existing static SDK-entrypoint direction can remove work rather than merely overlap the small prerequisite. The profile parent chain proves that process is inside SDK loading; it does not by itself identify the language or module by name.

Advertisement starts form several groups, but no queue-admission marker was collected. Module resolution already has bounded parallelism (eight jobs), and this fixture declares nine modules. Dependency/config readiness, vanity resolution and that queue can all affect probe start times. The data do not distinguish these causes, so neither a concurrency increase nor a claimed 385 ms saving is justified. A pin cannot replace the fresh per-session access boundary.

The two JSON files contain only fixed labels, numeric intervals/counters and profile hashes. Raw profiles and request metadata remain private. This report makes no production Cloud, full cold-start or universal 500 ms claim.
