# Isolated relay writer fairness correction

A local gated fake-transport test reproduces an actual scheduling flaw in the
measured v2 prototype. Its scheduler always scans from writer index zero; a
nonempty earlier writer keeps that position. With one worker, an earlier writer
that remains ready can keep receiving service while a later ready writer waits.
With four workers, enough continuously ready early writers create the same risk.

The candidate rotates the scan start after each successful reservation. Removing
an empty writer adjusts the cursor so it continues pointing at the same next
writer, or the next surviving one. The mutex protects the cursor and writer list.
Existing per-writer FIFO, single active request per writer, retry deadlines,
blocked-writer behavior, persistence/acknowledgement logic, and four-worker limit
are unchanged. Selection still scans at most the current writer count; no new
queue, retained payload copy or global cache is added.

Validation completed entirely with local fake transports:

- Frozen v2 fails `TestReadyWriterGetsBoundedTurn`: after `early/1`, it selects
  `early/2` while `late/1` waits and more early records remain queued.
- Candidate passes that test: `late/1` receives the next turn; early records then
  finish in their original order.
- A nine-writer, three-record test verifies per-writer FIFO, no concurrent export
  for the same writer, and a maximum of four active requests.
- The complete existing fake-transport suite plus new tests passed in 2.341 s.
- The two new scheduler tests passed with the race detector, three repetitions,
  in 1.426 s.

This corrects selection fairness. It does **not** show that fairness caused the
measured backlog, increase remote capacity, reduce HTTP request count, or prove
that the relay can sustain the desired command arrival rate. The measured
40-command v2 trial is unchanged and remains evidence for that exact prototype.

Files: `main.go` candidate, unchanged `control.go.txt`, copied `main_test.go`,
`fairness_test.go`, `fairness.patch`, `source-manifest.json`, and three test logs.
The live relay directory, binary, frozen source and telemetry snapshots were not
modified. No extra Cloud calls or engine benchmarks were run.

Reproduce from the repository root:

```sh
CGO_ENABLED=0 go test -modfile=/tmp/collections-perf/post-rebase-io/build.mod \
  /tmp/collections-perf/relay-fairness/main.go \
  /tmp/collections-perf/relay-fairness/main_test.go \
  /tmp/collections-perf/relay-fairness/fairness_test.go -count=1
```

Add `-overlay=/tmp/collections-perf/relay-fairness/control-overlay.json` and
`-run '^TestReadyWriterGetsBoundedTurn$'` to see the original failure. Use
`go test -race` with the same files and
`-run '^Test(ReadyWriterGetsBoundedTurn|RotatingSchedulerPreservesFourWorkerBoundAndFIFO)$' -count=3`
for the targeted race checks.
