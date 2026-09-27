The production registration snapshot reduced full check/artifact listing by about 0.53 s in this bounded local comparison, while preserving all 36 expected outcomes. It is a small current-branch change: one fresh, private metadata parse supplies both self-type names and object directives during each registration. Source evaluation still parses its own independent AST. No metadata is reused across registrations, sessions or source changes.

Both engines were built from clean `4f2ef6d700` using ordinary repository dependencies. The only candidate source replacements are `core/sdk/dang/v2/helpers.go` and the new `registration_metadata.go`. Control SHA begins `67bfc06c`; candidate `5536ea6e`. They use the same pinned d685 CLI, image/ordinary init, SDK artifact blobs and Address-enabled public Go module. These results do not describe the older experimental Dang/schema stack that produced the earlier ~1.1 s observations.

| Ordinary full CLI flow | Control median | Snapshot median | Reduction | Samples per arm |
| --- | ---: | ---: | ---: | ---: |
| `dagger check -l --all` | 3.595 s | 3.068 s | 527 ms / 14.7% | 2 |
| `dagger list -a` | 3.592 s | 3.065 s | 527 ms / 14.7% | 2 |
| Write a novel comment, then `dagger check -l --all` | 3.542 s | 3.069 s | 473 ms / 13.4% | 3 |

These are four correlated ABBA blocks on one retained engine volume, not a broad latency distribution. Each block starts a newly owned engine container and runs full check and artifact primers before ordinary samples. Both variants use the same restored fixture path. Every edited invocation receives a new equal-length comment nonce, so the other arm cannot prime exactly that edited source. Primers, version probes, actual checks, generation controls, profiles and engine provisioning/shutdown are excluded from the table.

All full check listings matched the ordered normalized 14-row golden. Every artifact listing matched the complete first-control output. Both current-production version probes passed. For each engine, a strict selected HTTP test first validated the actual service status/body and then hit the inserted failure sentinel; removing that sentinel produced exactly one passing selected check. Missing service configuration failed rather than skipped. These checks used the normal selected command with default generated behavior. Four authored native generations wrote their fresh expected bytes after removing the destination. The selected checks and native generations had no execution-specific primer, so their recorded times are correctness/first-demand controls, not warm speedup evidence.

The first control's full-check primer took 27.20 s on the retained volume. It is not a fresh-volume cold result. The first candidate reused the same volume later; its primer cannot be compared as a cold-start speedup. No Cloud data was sent, and there is no production Cloud or fresh-volume performance claim.

Two separately primed profiles explain the listing improvement:

| Inclusive diagnostic phase | Control | Snapshot |
| --- | ---: | ---: |
| Catalog, `Workspace.artifacts` | 2,366.36 ms | 1,906.82 ms |
| Collection expansion, `Artifacts.__itemsJSON` | 1,126.81 ms | 1,076.56 ms |
| Self-type metadata, union (10 calls) | 940.38 ms | 1,030.62 ms |
| Object-directive metadata, union (10 calls) | 974.31 ms | 0.0117 ms |
| Both metadata phases, union | 1,589.70 ms | 1,030.62 ms |
| Independent source evaluation, union (25 calls) | 1,843.00 ms | 1,938.01 ms |

The original object-directive pass parsed the files again. The candidate's corresponding phase only attaches already-read, private raw directives. Its summed duration drops from 1,177.98 ms to 0.0117 ms. The first metadata pass remains, and the 25 independent declaration/runtime source evaluations remain. The candidate's longer self-type/evaluation unions show why individual overlapping phases cannot be subtracted or added as whole-command savings. The separately profiled CLI times were 3.687 s and 3.175 s; ordinary samples above are the timing evidence. Both profiles have zero open operations, zero dropped events and no completed operations outside their CLI brackets.

Engine CPU also decreased in these ordinary observations. Warm check CPU was 12.80/12.86 core-seconds versus 10.96/11.01; artifact CPU was 12.76/12.55 versus 11.40/11.33. Across warm and comment samples, the host's full I/O pressure delta was at most 39.8 ms and the sampled engine writes were zero. These counters do not measure unsampled writeback or prove an absence of all disk effects. They support reduced CPU work in this run. The separate metadata microbenchmarks approximately halve allocation bytes/counts, but the snapshot holds directive nodes live across evaluation: no lower peak-memory claim is made.

The production patch preserves declaration order, main self-type fallback, best-effort names, private-object directives, original error precedence/rendering and an independently inferred AST. Six focused registration test groups, existing error-rendering tests and race tests passed before these builds, including actual DeclareDir/self-type/@collection behavior and edited-source independence. The three upstream files are helpers.go, registration_metadata.go and registration_metadata_test.go; lab-only baseline-copy/microbenchmark files should remain outside the production patch.

All six temporary containers were removed. The original engine and init stayed unchanged and stopped, the retained volume was preserved, and app/native/original public fixtures were fully restored. The 16 GiB free-space floor and cumulative 8 GiB CLI-bracketing write guard remained satisfied; setup/start/gap/stop writeback is outside that sampled write budget. Safe evidence includes source/build hashes, numeric results, reducer and restoration summaries. Raw stdout/stderr, profiles, payloads and binary copies remain private and are excluded from the archive allowlist.
