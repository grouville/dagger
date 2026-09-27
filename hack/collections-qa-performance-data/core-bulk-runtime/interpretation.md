This candidate remains isolated. The fresh library construction benchmark improves18.1%, but the ordinary retained-volume CLI run does not establish a useful general UX gain: first API after restart improves12.6ms at the median, while all three warm medians are worse. Four warm samples per variant cannot identify a small regression reliably, and there is no basis here to describe it as a warm optimization.

The separate profiles confirm that the consumer change executes and removes work. On the first API after another process restart:

| Profile observation | Baseline | Candidate |
| --- | ---: | ---: |
| All operations | 11,465 | 10,655 |
| `currentTypeDefs` inclusive wall | 321.42ms | 265.67ms |
| Object single attachments | 865 (783 hits,82 executions) | 41 (3 hits,38 executions) |
| Object bulk attachments | 0 | 86 (78 hits,8 executions) |
| Interface single attachments | 2 hits | 2 hits |
| Result publications | 435 | 399 |
| Function creation calls | 867 | 867 |
| Function-argument creation calls | 819 | 819 |

This is reconstruction through mostly persisted cache hits, not a fresh metadata cache. The candidate removes738 attachment calls and36 result publications in this diagnostic. The unchanged function and argument graphs still need resolution. This differs from the new-cache library workload, where every intermediate result needs publication.

The56ms diagnostic `currentTypeDefs` difference is not entirely attributable to the patch: attachment classes sum39.71→9.71ms, while the unchanged `Function.withDescription` class contains a12.61ms baseline outlier versus a0.20ms maximum in the candidate. Inclusive durations overlap; they are not additive predicted savings. The profiles are separate runs and cannot replace the ordinary CLI measurements.

Warm core/listing engine CPU medians are almost unchanged. Warm module CPU differs, but no separate warm profile was collected to assign that difference to a mechanism. The candidate does not establish a warm gain, and this experiment should not be extended into repeated sampling until one series happens to look favorable.

A future single-copy builder can attack the still-quadratic local `WithFunction` loop, but that is a different candidate requiring alias/replacement parity and independent evidence. It does not follow that this publication-only change should ship now.
