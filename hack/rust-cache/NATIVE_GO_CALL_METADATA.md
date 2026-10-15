# Read Go module call metadata in one request

The generated Go entrypoint reads the parent type, function name, parent JSON
and input argument IDs in four requests. It then fetches each argument's name
and JSON value separately. Starting a function with N arguments therefore takes
4 + 2N metadata requests before invoking user code, even on a warm engine.

The Go compiler submodule has eleven arguments: 26 requests. The variant reads
the same fields in one ordinary GraphQL query and constructs the same argument
map. Function invocation, JSON decoding, result marshalling and error reporting
remain in the generated entrypoint. No engine API or dependency is added.

The [generator change and executable regression](https://github.com/grouville/dagger/commit/160e805e8)
are separate from the Rust cache work and based on upstream main `5d313bf2e`.
The [Rust compiler entrypoint](https://github.com/grouville/dagger-rust/commit/cb3278b)
uses the dispatch function emitted by that generator, with ordinary Go formatting.
The surrounding Rust module is `a8ede44`; its Dang source and compiler execution
programs are unchanged. Existing Go modules need regeneration to use the change.
Both branches are pushed to Guillaume's forks; no upstream PR is open.

## Verify generated behavior and native reuse

The regression compiles the emitted entrypoint against the real Go SDK and
executes it against a local metadata server. It checks module initialization,
a method without arguments, escaped and Unicode JSON, nulls, booleans, nested
values, an opaque directory ID, a user-function error and a metadata error.
The returned parent and argument bytes must be identical. The two error cases
must report the correct original message through the SDK.

On unmodified main, successful zero-argument calls make four metadata requests
and the five-argument case makes fourteen. The final code makes one in every
case. The regression fails on the request count against main and passes under
race detection with the patch. Existing Go generator and template suites also
pass under race detection.

A bridge against a currently verified history recovers 130/130 native compiler
results with either entrypoint. The worker build excludes the generated module
entrypoint, so its native compiler compatibility identity is unchanged.
Post-timing probes recover 130/130 workspace results and 6/6 collection results
for both variants. Fresh leaf edits have two execution markers; application
edits in the collection have four. The changed entrypoint rejects invalid Rust,
then passes the actual package tests after source restoration and recovers all
six existing compiler results.

An earlier bridge attempt used a project key whose history had been wiped by
the previous experiment's forced engine stop. It reported zero reuse. The
current-history bridge first checks the control's 130/130 reuse before trying
the changed entrypoint; both pass. An unavailable history is not used as evidence
of an entrypoint compatibility problem.

## Profile the actual Rust command

Two fresh leaf-edit wcprof captures have no dropped events or open operations.
They use the same engine and independently prepared source trees:

| Work in the capture | Previous entrypoint | Batched entrypoint |
| --- | ---: | ---: |
| Call-metadata requests | 26 | 1 |
| First metadata request through last response | 24.70 ms | 6.21 ms |
| All recorded engine requests | 110 | 85 |

The metadata interval includes the gaps between these sequential requests.
This locates an 18.5 ms reduction in one capture. It is not an additional saving
to add to complete-command timings.

## Complete edited commands

Both versions run on the same unchanged warm engine, with independent native
histories, source trees and Cargo targets. Invocation order rotates. Every
command follows a new source edit, using distinct values for each variant.
Telemetry remains enabled and wcprof is off. Rust 1.77.2 uses eight jobs. The
timer uses blocking `waitpid`, without timeout polling. Two preparation rounds
are excluded from each series. No unrelated build or test runs during timing.

Eight pairs per scenario:

| Scenario | Control median | Batched median | Cargo median | Median paired saving | Faster pairs |
| --- | ---: | ---: | ---: | ---: | ---: |
| 130 crates, leaf edit | 0.779 s | 0.757 s | 0.096 s | 15 ms | 6/8 |
| 130 crates, shared edit | 1.418 s | 1.426 s | 0.596 s | −12 ms | 4/8 |
| Actual package test collection | 0.995 s | 0.996 s | 0.481 s | 15 ms | 5/8 |

The module implementations are then swapped between those same histories,
without restarting the engine. Two preparation rounds precede eight more pairs:

| Scenario | Control median | Batched median | Cargo median | Median paired saving | Faster pairs |
| --- | ---: | ---: | ---: | ---: | ---: |
| 130 crates, leaf edit | 0.793 s | 0.775 s | 0.096 s | 8 ms | 5/8 |
| 130 crates, shared edit | 1.412 s | 1.440 s | 0.758 s | −27 ms | 3/8 |
| Actual package test collection | 1.020 s | 1.025 s | 0.483 s | 40 ms | 5/8 |

The first series has at most 2.8% host I/O stalls; its crossover reaches 63.1%.
All samples remain, including the crossover's 5.663 s control shared edit and
4.714 s Cargo shared edit. Column medians and median paired differences are
both retained; one must not be substituted for the other.

The request reduction and generated behavior are established. Leaf and
collection command benefits are modest and inconsistent; shared edits are
slower in both series. This does not establish a general command improvement,
and the variant remains isolated pending review and further attribution. The
Cargo +0.5 s target is still not established. The selected source-projection
improvement remains separate.

The next costs are visible in the same candidate capture. The package-digest
request takes 87.5 ms. The compiler execution request takes 161.6 ms, including
73.9 ms in its program and a 33.6 ms chain of directory copies before execution.
Runtime start itself takes 2.8 ms. These intervals locate preparation work to
investigate; they are not independent savings. The
[compiler-request critical path](experiments/native-go-call-metadata/worker-request-critical.txt)
preserves the breakdown.

The [measurements](experiments/native-go-call-metadata/measurements.json) retain
all timing and pressure samples, profile summaries and correctness outcomes.
The experiment directory also contains the local measurement and profile drivers.
