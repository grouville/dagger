# Listing allocation stacks point back to telemetry conversion

A fresh 1,026-package listing allocates **2.27 GB** during the command on the selected engine. The Protobuf field-ordering frame appears on **17.6% of sampled allocation stacks**, but this includes encoding performed through its visitor callback. Subsequent source-line analysis attributes about **94 MB to the reflective-sort call itself**. Stored-span fetching and repeated telemetry conversion are also large callers. These are profiling targets, not established performance improvements.

The complete-command comparisons in [the mirror study](NATIVE_MIRROR_METADATA.md) already show roughly 2.25 GB allocated per listing under ordinary GC. The new capture uses the same selected engine `f73ec4d9…`, Rust module `da1ae47`, telemetry enabled and a fresh used source edit. It validates all 1,026 expected package names.

## Measure allocation stacks rather than infer them from CPU

The first five-second delta profile is misleading for request attribution: most sampled bytes belong to cache maintenance after the listing finishes. Go's memory profile can lag recent allocations by up to two GC cycles. That capture, its CPU profile, CLI trace and complete wcprof dump remain archived; its allocation totals are not used to describe the listing.

The second diagnostic takes cumulative allocation profiles before and after a fresh edited listing. Two explicit Go GCs at each boundary flush delayed samples. The command's allocation counter increases by **2,271,287,568 bytes**; the broader sampled window accounts for about **2.42 GB**, including boundary and background work. The forced collections make this unsuitable for latency comparisons. They are not part of any benchmark cohort or production policy.

| Sampled cumulative caller | Share of sampled bytes |
| --- | ---: |
| Stored-span batch fetching | 22.9% |
| Protobuf JSON marshaling | 20.4% |
| Protobuf field ordering | 17.6% |
| SDK spans converted to Protobuf | 16.6% |

These caller stacks overlap and must not be added. In particular, the field-ordering total includes its visitor's encoding allocations. The source-line report records 93,850,996 sampled bytes at `sort.Slice`, about 3.9% of the broader capture; the cumulative percentage cannot be treated as removable sorting overhead. The normal wcprof capture also shows result publication and artifact field evaluation on the listing's critical path, so allocation reduction still needs complete-command validation.

## What to test next

There are already isolated [direct span conversion](NATIVE_DIRECT_SPAN_FORWARDING.md) and [spill-buffer reuse](NATIVE_TELEMETRY_READ_BUFFERS.md) experiments. This profile is new evidence for their callers, not a new discovery of those candidates. The direct converter has mixed historical command results; spill-buffer reuse is one of the eight prepared upstream proposals.

The [field-sorting follow-up](NATIVE_PROTOBUF_FIELD_SORTING.md) now tests both small-message fast paths and a typed sorter for larger messages. Components improve, but two complete-command cohorts per variant remain mixed, so both stay disabled. It also narrows the actual reflective-sort allocation to about 94 MB. The earlier generic `slices.SortFunc` substitution slowed larger messages and remains rejected; the typed `sort.Interface` screen is a separate implementation.

No production code, cache identity or selected configuration changes in this study. The final runtime check confirms the selected binary, normal snapshot collection, no active sessions, and profiling and temporary controls off. The upstream batch stays at eight; the Rust-cache goal remains incomplete.

[The archive](experiments/listing-allocations/) contains both captures, exact drivers and source edits, before/after allocation and heap profiles, pprof reports, wcprof, raw counters and final engine state. Its README gives the allocation comparison command and links the unchanged engine source manifests. The archive excludes binaries, volumes and target directories.
