# Avoid eager Unicode width-table construction at CLI startup

Update the existing indirect `github.com/mattn/go-runewidth` dependency from
v0.0.27 to v0.0.30. The released implementation initializes a small low-rune
table eagerly and constructs the higher-rune table lazily, with synchronization.
There is no Dagger-local table implementation, dependency replacement, engine
change, cache bypass, listener, or session-lifecycle change in this fix.

## Context and mechanism

Fresh standalone commands paid for v0.0.27's width-table construction before the
root trace started. `GODEBUG=inittrace=1 dagger version` identified about 22 ms
in that package's init. The same diagnostic on the candidate records 0.082 ms.
These individual init traces explain a mechanism; they are not headline timings.
The full command comparisons below use neither `GODEBUG` nor an init tracer.

Both CLIs are built from parent 47a552be8acb2e76768f74d0cb4c85d843cfc218,
which contains upstream main 7c35e6274737acff0f6bd76614abb5e04efa7d12 and the
separately measured HTTP-preconnection change. Only go.mod/go.sum differ.
Main was independently rechecked before publication and had not changed.
Go 1.26.8, build flags and injected version metadata match on both sides.

## Measured pilot

Times are milliseconds. All pairs, including losses, are retained in
`results.json`. Savings are calculated per pair before taking the median;
they need not equal the difference of the two marginal medians.

| Standalone flow | Pairs | A median | B median | Paired saving median [min, max] | Favorable | p95 A -> B |
|---|---:|---:|---:|---:|---:|---:|
| version, no engine | 20 | 51.456 | 27.019 | 24.368 [22.169, 38.436] | 20/20 | 57.194 -> 29.246 |
| exact cached check | 12 | 399.654 | 376.852 | 23.456 [-22.196, 85.266] | 9/12 | 450.154 -> 420.962 |
| novel application edit | 10 | 764.172 | 743.502 | 39.815 [-62.490, 70.208] | 7/10 | 835.830 -> 818.437 |
| novel workspace-library edit | 10 | 918.158 | 887.086 | 17.165 [-87.404, 90.563] | 6/10 | 979.549 -> 992.745 |

The library tail regresses slightly. Engine/Cargo variability remains; do not
attribute the entire 39.815 ms paired application saving to a 22 ms init change.
This is one retained engine and two independent mutable Cargo caches, not ten
fresh-engine pairs. Each series excludes one explicitly labeled warmup pair.
Ordering alternates. Both fixtures are primed with the control CLI before A/B.
Application and library changes are matched byte-for-byte between the fixtures;
separate cache keys prevent the second command becoming a shared exact hit.

Ordinary `dagger check rust:check` commands run as new processes/sessions without
a listener. Headline checks omit `--profile` but export local OTLP. Separate
profiled companions cover three pairs each for exact/application/library, plus
their warmups. All 24 wcprof completeness/count/execution gates and 44 ordinary
edit execution/affected-crate gates pass. Replay drift is -0.0% to -0.2%.
Exact hits execute no Cargo; each novel edit executes Cargo once. Ordinary
application edits check only ripgrep; library edits check grep-printer, grep
and ripgrep. No warm image transfer occurs.

All nine non-warmup profiled pairs save time before the root trace: median
22.398 ms exact, 22.576 ms application, 23.510 ms library. Root-span timing is
variable; startup savings must not be reported as engine execution savings.

## Correctness

With the candidate dependency and the same Go environment:

```sh
go test -mod=readonly -race -count=1 github.com/mattn/go-runewidth
go test -mod=readonly -race -count=1 -run '^TestRuneWidthConcurrent$' github.com/mattn/go-runewidth
go test -mod=readonly -race -count=1 -run '^TestWriteWorkspaceSettingsTable(FitsViewWidth|MeasuresUnicodeWidth)$' ./internal/cmd/dagger
```

All pass (9.345 s, 1.187 s, 1.154 s respectively). The separate concurrency
process matters: the full dependency suite initializes the high table before
its concurrency test. The Dagger tests exercise CJK/emoji, valid UTF-8 and
bounded display width. The dependency retains exhaustive RuneWidth checksum
coverage for both East Asian modes. Its newer release also contains grapheme
and wrapping corrections; this is not a claim that every older API behavior
is byte-for-byte identical. The terminal recorder was unavailable, so no
recorded-screen QA claim is made. No macOS/remote runtime validation here.

## Reproduction and evidence

`build.sh`, `pilot.py`, `compare-cli-edits.py`, and `analyze.py` are frozen
copies of the executed controllers. Their owner paths and hash checks are
intentional provenance, not a portable install script. Do not rerun a completed
owner or remove its capture: it is single-use and fails closed. To reproduce,
use a new owned directory, rebuild both CLIs from the recorded parent with the
same flags, provision the same engine/module, then adapt only paths and
resulting build identities explicitly in a new controller before timing.

The pilot uses the maintained `hack/bench-rust-loop/run.py` and `compare-cli.py`
from the recorded engine source, primes both fixtures with A, then invokes:

```sh
python3 pilot.py --execute
python3 analyze.py
```

The analyzer requires the separately installed maintained wcprof executable;
its binary and raw profiles are not redistributed. `results.json` retains all
paired command timings and per-profile/per-edit gate results without raw OTel
records. `capture-manifest.json` records source identities, exact argv, fixture
paths, teardown and capture hashes. The measured source and raw evidence remain
unchanged in the original owner `/tmp/dagger-cli-runewidth.lhU4UO4i`.

Key identities:

- Control CLI: 23cb7f91c8c346741d349af1b98ba7fd553b160d3f09c56b508bae2fb0e30270
- Candidate CLI: ff1ef25902a037b41e8b16372fcdb806c0cffdd1568a0b9ed75b4e1ef1631f51
- Engine: sha256:c057d7eed790760d88e4cffb0f540adb9e230823b81759c0e86eeaae49d141a0
- Original module main.dang: f6e119c3b7be439df46a6ea9b74c368126751e0a141b2e5ebb699a4b0f0681f1
- Ripgrep: 3fce3b5bb0236da2df6d99672afb8a719642eca7
- Raw OTLP: 42,414,681 bytes, SHA256 2f78fff1bbeef198c4edf737bcac1c38da1677c48a56eac7098c02aa29b380c8
- Full report: 6a9055fba82c8dcbcf808dd2db0c83dda440e70c567496a304691656db2835c1
- wcprof: de3bde25361254d784a211a9fdfec5043459a7a211b9e2a012252ebfbd45a8ba

The retained engine identity is checked before and after. Only owned primer
containers are removed and independently verified absent; existing engine caches
are not reset. The local receiver exits after capture. Raw telemetry, binaries,
private analyzers and images are not uploaded.

## Limits and next step

No cold/onboarding, native-Cargo A/B, dependency-upgrade, build.rs/features,
artifact, fmt/clippy/test-command, concurrent-CLI, macOS or remote performance
claim. This is a narrow startup win, not a completed Rust performance goal.
Do not subtract it from an old cold measurement or add unrelated cohort gains.
Cold image delivery remains the seconds-scale priority for the next experiment.
