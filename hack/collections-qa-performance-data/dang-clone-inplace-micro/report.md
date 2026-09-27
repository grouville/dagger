# In-place Dang syntax cloning: isolated allocation improvement

The candidate passes focused normal/race checks and improves cached parsing of three real module sources in a small paired microbenchmark. No engine or whole-CLI measurement has been performed. This is a new change relative to the already-retained scalar/nil fast path, not a remeasurement of that earlier improvement.

The effective baseline is `b0f575ce0e8c7acc803e9aa7ae73e2a4da5d7b55ba21b2d02cdb04a0805258a0`, copied from diagnostic engine 6a82's frozen overlay. Candidate source is `7b0a1e382973d482ab68ac16e82e369323e44e5f37c9914f7c97f83c8166836e`; both arms include the same retained Dang fields/evaluation changes.

## Change and ownership

Previously, cloning a pointer allocated its target node, recursively allocated another temporary struct, then copied that struct into the target. Struct fields and slice elements likewise received detached temporary values despite already having owned destination storage. The new visitor writes those composite children directly into their fresh destination. Map entries and interface payloads retain a detached-value helper where reflection requires one, including the existing primitive/nil fast path.

Traversal remains O(visited values), with the same 262,144-visit bound and pointer-identity lookup. Each mutable syntax graph remains independently owned. Pointer aliases/cycles within one clone are preserved; no parsed template, client, inferred type environment, module scope or evaluated result is shared. Cache identity, source-byte hashing, entry/size bounds, parse failure fallback and source invalidation remain unchanged. Unsupported kinds, nonzero private fields and function-whitelist errors retain their existing behavior. SourceLocation filenames are still rewritten separately for each invocation.

## Correctness gates

The unchanged effective baseline and candidate passed the same normal gate; the candidate then passed the race gate. Package runtimes were 0.261s/0.258s/4.396s; those are test runtimes, not benchmark claims. The test set combines existing cache isolation/content edits, concurrent real inference and capacity tests with earlier scalar/nil ownership tests and three new destination-specific cases.

New cases verify nested value structs and interface payloads; shared pointers across fields, maps and slices; cycles; two independent clones; source-position rewriting; exact rejection messages; typed nil roots; and the exact traversal-budget boundary against an embedded copy of the retained baseline visitor. The latter finds the old threshold and checks the sizes immediately around it rather than assuming FileBlock's current layout.

## Paired local microbenchmarks

Two library binaries were compiled once with the same Go toolchain, CGO disabled and GOMAXPROCS=4. Three cycles used alternating order A/B, B/A, A/B, 200ms per case. Every process repeated the ownership/error gates. No engine, Docker, network or Cloud command ran. The real-source cases read/cache/clone original 1784 Go, gomod and GoDev files; source bytes are pinned in `benchmark-builds.json`. Both same-path and alternating-path cases are primed outside timing and validate fresh source locations. The mutable 1,024-declaration cases mutate returned nodes and verify that templates remain unchanged. No inference or module execution occurs in the timed region.

| Case | Retained baseline | In-place candidate | Time | Bytes/op | Allocations/op |
| --- | ---: | ---: | ---: | ---: | ---: |
| syntax: declarations=1024 | 15.709 ms | 11.679 ms | -25.7% | 5,776,400 → 4,571,976 | 72,861 → 26,774 |
| syntax: declarations=128 | 1.830 ms | 1.507 ms | -17.7% | 718,928 → 568,200 | 9,130 → 3,363 |
| syntax: declarations=16 | 0.238 ms | 0.186 ms | -21.9% | 86,720 → 67,704 | 1,162 → 435 |
| module: .dagger/modules/go-dev/main.dang/alternating-paths | 8.149 ms | 6.928 ms | -15.0% | 3,059,292 → 2,400,240 | 40,481 → 14,768 |
| module: .dagger/modules/go-dev/main.dang/same-path | 8.552 ms | 7.241 ms | -15.3% | 3,059,288 → 2,400,240 | 40,481 → 14,768 |
| module: go.dang/alternating-paths | 4.569 ms | 3.600 ms | -21.2% | 1,612,458 → 1,237,824 | 23,041 → 8,653 |
| module: go.dang/same-path | 4.577 ms | 3.506 ms | -23.4% | 1,612,443 → 1,237,808 | 23,041 → 8,653 |
| module: gomod/main.dang/alternating-paths | 4.072 ms | 3.565 ms | -12.4% | 1,514,176 → 1,194,120 | 19,648 → 7,423 |
| module: gomod/main.dang/same-path | 4.171 ms | 3.359 ms | -19.5% | 1,514,177 → 1,194,120 | 19,648 → 7,423 |
| mutable: declarations=1024/alternating-filenames | 15.427 ms | 12.281 ms | -20.4% | 5,776,400 → 4,571,976 | 72,861 → 26,774 |
| mutable: declarations=1024/same-filename | 16.065 ms | 12.260 ms | -23.7% | 5,776,408 → 4,571,976 | 72,861 → 26,774 |

Real-source same-path medians improve 15–23%, allocation counts 62–64%, and bytes 21–23%. Across the 33 case/cycle pairs, 32 are faster; the remaining gomod alternating-path observation is 7.3µs slower. Three repetitions are a directional engineering witness, not a distribution or universal latency guarantee. Removing intermediate reflection boxes reduces allocation overhead, but the owned AST, pointer-alias map, file read/hash and remaining reflection still exist.

Current discovery's 81ms source-evaluation union also includes import construction, inference and evaluation, and overlaps nested invocation waits. These microbenchmark gains must not be multiplied by 15 calls or transferred directly to CLI wall time. A matched full-engine comparison is required before adoption.

## Upstream boundary and next gate

This patch improves the experimental syntax-cache dependency already used in the lab. It does not make that cache generally upstream-ready: generated typed cloning or an explicitly immutable syntax representation remains a maintenance question. The current change is independently reviewable, has no public API or source-identity change, and does not reuse evaluated state. The next allowed step is parent source review followed by a separate matched engine/profile comparison if warranted; none has run yet.

`prototype.patch` is relative to the effective retained leaf-fastpath baseline. The isolated overlays preserve the dependency checkout. `validation-results.json`, `benchmark-builds.json`, `benchmark-runs.json`, and `numeric-evidence.json` record exact commands, hashes, raw numeric observations and medians. Source copies in the archive use `.go.txt` suffixes to avoid creating accidental Go packages.
