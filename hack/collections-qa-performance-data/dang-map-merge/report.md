# Linear immutable map merging in Dang

An isolated prototype changes the existing `Map.merge` builtin from repeated
whole-map copies to one private builder. For two disjoint maps with 512 entries
each, the median of three short process pairs is **21.395 ms → 0.068 ms**;
allocation volume is **33,041,792 → 100,576 bytes/op**. This is a library
microbenchmark, not a new greetings-api latency result. The measured small
listing has not shown this builtin on its critical path.

The original merge calls immutable `With` for each of the right-hand map's m
keys. Each call copies the growing left-hand map and its ordered key slice.
With n initial entries, that requires O(nm + m²) copying for disjoint maps.
The candidate allocates its own map and key slice once, copies the left-hand
state once, then visits the right-hand keys in insertion order. Expected work
is O(n + m), with O(n + m) storage, using an ordinary Go hash map privately
before publishing the resulting immutable value.

The public API, receiver value type, key order, replacement semantics and
shallow sharing of nested values are unchanged. Existing keys keep their
position; new keys follow right-hand insertion order; right-hand values win.
Empty merges retain the original no-op behavior. This does not make repeated
user-authored `Map.with` calls linear: bulk construction or a separately designed
persistent representation would be needed for that different operation.

| Entries per input | Overlap | Baseline | Candidate | Allocation bytes before → after |
| --- | --- | ---: | ---: | ---: |
| 1 | none | 468.4 ns | 444.1 ns | 480 → 464 |
| 1 | all | 438.6 ns | 443.6 ns | 448 → 464 |
| 8 | none | 8.543 µs | 1.280 µs | 10,976 → 1,592 |
| 8 | all | 6.056 µs | 1.339 µs | 6,432 → 1,592 |
| 64 | none | 357.013 µs | 7.972 µs | 514,528 → 11,960 |
| 64 | all | 244.067 µs | 8.179 µs | 390,752 → 11,960 |
| 512 | none | 21.395 ms | 67.870 µs | 33,041,792 → 100,576 |
| 512 | all | 14.040 ms | 68.744 µs | 25,866,336 → 100,576 |

The one-key replacement case allocates 16 extra bytes and has a small timing
increase; this implementation reserves worst-case key capacity even when all
keys overlap. Avoid claiming an improvement for every input size. Large cases
complete only 5–8 baseline iterations per 100 ms run. Three alternating process
pairs establish the algorithmic trend, not a broad latency distribution.

Both variants use an exact private copy of ordinary Dang v2.1.4 and the same
Go 1.26.6 toolchain, GOMAXPROCS=4, CGO disabled for ordinary runs. The experimental
syntax cache is absent. Two binaries are compiled once; fixture construction
is outside the timed region. The timed calls execute the actual registered
builtin, verify successful result size, and report allocations. `numeric.json`
retains all 48 observations, iteration counts and input/log hashes.

Five focused correctness groups pass on the baseline and candidate, then on
the candidate with the race detector. They cover collisions and ordered keys,
empty/self merges, wrong argument rejection, 200 deterministic reference cases,
independent mutable containers, concurrent callers and actual parse/infer/eval
of a Dang program asserting both result and unmodified inputs. Each benchmark
process reruns these gates. No engine, Docker, registry or Cloud workload ran.

Two harness setup errors are preserved: Go rejects overlays beneath GOMODCACHE,
so the exact dependency was copied privately before compilation; a subsequent
manifest incorrectly included a generated log and stopped after the successful
baseline gate. Removing that output from source guards allowed the same passing
step to be retained and the remaining gates to run. Neither correction changed
production source or test assertions.

This small patch is an upstream candidate for Dang, independently of Dagger's
SDK and distributed-cache work. It is not installed in either engine used by
the simultaneous discovery comparison. `prototype.patch` applies to
`pkg/dang/stdlib.go`; the focused test file can accompany it upstream. The local
driver and source inventory are attribution artifacts, not production code.
