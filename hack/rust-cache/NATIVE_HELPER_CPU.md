# Profile the actual Go compiler helper

Engine pprof does not include CPU used by the Go module process. A separate diagnostic module samples CPU and blocking while `RustCompiler.Compile` runs, and wcprof captures the enclosing engine operations. This exposes plan decoding, graph construction and request serialization without treating all time between engine requests as computation.

The profiler starts at entry to `Compile` and stops on its return. It includes all Go process goroutines active in that interval, including telemetry and garbage collection. Generated argument decoding before entry and result serialization after return are outside the capture. Profiling shutdown adds latency, so none of these commands enters the unprofiled performance comparison.

Profiles are encoded into a diagnostic stderr record and recovered through `hack/otlpdump`. Successful CLI summaries omit that record, even with verbosity enabled. The initial CLI-only extraction failed; raw telemetry recovers the profiles. Both diagnostic modules use the same two-line entrypoint patch and profiler implementation, with no generated SDK modification. The normal modules contain no profiling code.

## Exploratory captures

Nine fresh normal commands cover three edits each in the 130-crate direct check, 1,026-crate collection check and small collection tests. Every wcprof capture has zero dropped events and open operations. This series has no quiet-start admission and encounters substantial host pressure; its wall times are diagnostic observations only.

Two large captures each sample 310 ms of Go process CPU. JSON encoding and decoding, memory copies and allocation are prominent. The retained large plan is 2,528,109 bytes, including 2,100,654 bytes of actions. Commands and environments occupy most of the action data. The worker request repeats the full action table even when only two actions execute.

Block profiles primarily show engine requests and background goroutines waiting on channels. Background telemetry goroutines can wait throughout a command; their accumulated block time is not exporter CPU or additive command overhead. These profiles do not justify removing telemetry.

The first two 130-crate captures spend about 1.6–2.3 ms total in newly executed checkpoint resolvers. One large checkpoint reaches 36.6 ms. Resolver intervals exclude client transport and request construction, so they do not prove total retention is cheap. The large source-path glob varies from 45 ms to 1.185 s across two captures and can include prerequisite evaluation. These observations alone do not justify checkpoint batching or identify the cause of every pause.

## Confirm the smaller dependency request

The [eight-line dependency request change](NATIVE_WORKER_REQUESTS.md) is profiled independently after its unprofiled comparisons. Each diagnostic module is prepared once; four fresh large-workspace captures then run in A/B and B/A order on the same physical source history. Their wcprof captures have zero dropped events and open operations.

| Diagnostic observation | Before | Compact dependency table |
| --- | ---: | ---: |
| Compile intervals, two calls | 830 / 858 ms | 667 / 696 ms |
| Total sampled process CPU, two calls | 420 ms | 290 ms |
| Cumulative samples through JSON marshal | 120 ms | 60 ms |
| Cumulative samples through JSON unmarshal | 80 ms | 110 ms |

These small profiles include process background work. They support less serialization and copying; they do not establish a precise general CPU saving. Plan decoding and compiler/snapshot work remain. The separate timed commands have profiling and wcprof disabled.

The engine remains `a75afeec2c7fa014af451b8ba2eb87f1273990a83b2a5e45944031dd9da4aeaa`. Source snapshot seeds, compact scalar restoration, batch metadata reuse and the attribute-array decoder match in both arms. Telemetry stays enabled. The recording receiver is stopped after capture; the engine and cache volume are preserved, and diagnostic modes are restored.

Evidence includes exact instrumentation, source bases and hashes, raw CPU/block profiles, compressed wcprof captures, setup records and textual summaries: [compiler-helper-cpu](experiments/compiler-helper-cpu/). The much larger original OTLP JSONL remains local and is excluded. Paths and receiver addresses in the drivers need adjustment elsewhere.
