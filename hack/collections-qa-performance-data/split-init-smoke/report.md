# Split-init correctness smoke: passed, before timing

All ten explicitly counted local calls passed. These are setup/correctness calls; initial SDK setup and their profiled wall times cannot be used as an A/B speed comparison.

| Flow | Baseline setup/validation | Candidate setup/validation | Process runs, baseline / candidate |
| --- | ---: | ---: | ---: |
| go-read | 0.985 s | 0.782 s | 2 / 2 |
| ts-read | 10.844 s | 2.125 s | 7 / 3 |
| ordinary-exec | 3.754 s | 0.540 s | 1 / 1 |
| greetings-check | 12.441 s | 12.110 s | 8 / 8 |
| python-read | 24.614 s | 3.272 s | 13 / 3 |

The Go gate returned exact main.go contents through the authored Backend constructor. The TypeScript gate called the real Frontend.build and returned exact index.html contents. Both existing modules disable default function caching, preventing registration-only results from standing in for their runtime calls. The Python module used the repository constructor-default-factory body and a per-session configuration; it returned the expected File content through the actual Python SDK. Its first standard SDK preparation was included in the baseline gate (24.614 s), not hidden in a primer. Differing TS/Python process counts reflect that setup boundary.

The ordinary container exec used unique arguments and asserted the actual mounted init hash; the split arm also asserted the helper hash, while the control required that helper mount to be absent. It returned the exact marker. The selected TestFormatResponse check used a unique t.Log string in its existing body to change the test binary without changing discovery keys, and reported one passing check in each arm. All ten profiles had actual exec.processRun operations, zero unfinished operations and zero dropped events. Those aggregate counters alone do not classify every process as authored code; the independent source/behavior checks provide that additional evidence.

Both arms installed identical pinned heavy/light helper binaries and used original CLI d685. The engines differed only in the split-init prototype. Original fixtures, original engine and its heavy init were preserved; the retained volume remains and only the owned temporary container/fixture copy were removed. Zero Cloud calls ran. The separate36-command ordinary ABBA stage has not run yet.
