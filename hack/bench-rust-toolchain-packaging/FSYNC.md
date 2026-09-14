# Cold ingest sync: measured kernel writeback waits

2026-09-14. **Diagnostic checkpoint, not a new engine fix or speedup.**
The [relay scorecard](RELAY.md) remains the latest ordinary-CLI A/B cohort and
still loses native Cargo in every flow median. This single instrumented capture
investigates sync cost; it does not replace those results or meet the Rust goal.

## What was observed

One fresh Rust-absent engine, frozen relay 7a27/CLI 6a5/full standard flat Zstd
toolchain/prebundled module, pinned ripgrep and the same Cargo check as RELAY.md.
Empty introspection provisions the engine before tracing. A bounded kernel
collector then brackets the complete standalone profiled check. No native
comparator, full-install timing or controlled A/B performance result here.

| Measurement | Milliseconds |
| --- | ---: |
| Profiled check, excluding provisioning | 10387.236734 |
| Whole Rust image delivery envelope | 3012.998004 |
| Source reconciliation and Cargo | 6441.280755 |
| Large-layer metadata preSync | 143.151066 |
| Corresponding ingest-file fsync syscall | 143.137165 |
| Off-CPU within that syscall | 125.315946 |
| Off-CPU: block-writeback throttling | 112.039462 |
| Off-CPU: file-writeback completion | 8.920909 |
| Off-CPU: journal-commit completion | 4.355575 |
| Non-off-CPU syscall residual | 17.821219 |
| Ordinary exact followup | 564.969184 |

The three wait groups partition that syscall's off-CPU intervals. Kernel stacks
identify `wbt_wait`/`rq_qos_wait`, `folio_wait_writeback`, and
`jbd2_log_wait_commit`. Off-CPU includes wakeup-to-run scheduling delay; the
residual includes execution and probe overhead, not an independent CPU profile.
Do not add inclusive parent/child durations or treat waits as predicted savings.

The 143.151ms preSync span maps uniquely to the 143.137ms successful filesystem
call. Source inspection confirms this is before the Bolt metadata transaction;
content-lock acquisition and the later file/directory syncs have separate spans.
Both relay arms have identical code in this content-store path.

The earlier **8.109920s stall did not recur**. This does not explain that old
run retroactively or justify removing it. The normal sync is a smaller target
than the remaining ~3s image phase; wcprof still shows 2.73s in HTTP body lifetime,
which includes local consumer backpressure, not just network delay.

## Validation and scope

- Maintained wcprof: 289 operations, one root, zero open/dropped, 271 declared and
  received spans, structural PASS and -0.1% replay drift against the unchanged
  absolute 2% gate. Full 298210801-byte layer transfer, expected cold crate set,
  Rustup/Cargo execution and cache-snapshot parsing pass. No execution/image work
  in preprovision or the ordinary exact followup.
- Kernel counts exactly match emitted records: 9 fsync entries/exits, 9 ext4
  entries/exits, 33 off-CPU intervals, 115 journal and 32330 block records. No
  unfinished maps or unresolved stacks. Entry/exit durations and off-CPU sums
  agree. Separate clock/identity gates cover the entire image AND CLI process
  within actual READY..STOPPED boundaries, with 1643ns clock uncertainty.
- The initial controlled collector test lost device records despite empty stderr.
  It was rejected. Explicit armed boundaries, a drain phase and exact counter
  equality now guard against silent loss. Positive and six malformed/incomplete
  analyzer fixtures pass; the controlled 64MiB file test is not Rust evidence.
- Engine TGID is resolved and checked against its owned container/executable and
  parent chain; Docker's init PID is not used as a substitute. Device events are
  filtered to the actual ext4/NVMe backing device, not to the engine PID, because
  writeback/journal completions are asynchronous. The 4319 block and 5 journal
  records within the sync can include unrelated host work. Sector/length are not
  unique request IDs; no per-request queue/service latency is inferred.
- Probe runs in a disposable network-disabled, read-only container with only
  tracing/resource capabilities. No sudo password, global sysctl/cache/security
  change, SYS_ADMIN or writable host mount. Docker's automatic `label=disable`
  for host PID mode is recorded; mandatory no-new-privileges remains. All owned
  registry/engine/probe resources are removed and prior inventory is restored.

A first Rust capture failed its security-option guard before executing Rust.
Its receipt and interrupted output are retained. A new owner retries only the
verified Docker host-PID option handling and output/resource identities; no
measurement/correctness gate is weakened or failed sample called a speedup.

## Reproduction and next decision

Local owner: `/tmp/dagger-fsync-capture-r2.WtSjuoyr`; calibration and rejected
attempt: `/tmp/dagger-fsync-tracing.aYIPHkaF`. Frozen `capture.py --plan`, then
`--execute`, validates full OCI bytes and creates fresh owned resources. After
capture, run `analyze.py`; `analyze-kernel.py` with kernel.jsonl, its stderr,
receipt.json and analysis/rust-absent-check.trace.jsonl; then `gate-coverage.py`.
Refuse existing outputs; use a new owner for a rerun. Normal collector termination
has an armed 45-second interval plus two drain ticks; time alone is not proof of
record completeness. Provisioning's 965.791ms must not be added to this check to
manufacture an ordinary first-command score.

This is not yet a turnkey public runtime reproduction. Tools/images/modules and
the private local registry are preinstalled; host page caches remain. No public
CDN/authentication, shared-base, macOS/remote, full installation, Clippy/tests or
build/artifact-export claim. No raw kernel/OTLP profiles, private analyzer,
credentials, public image, PR or maintainer approval is published.

| Retained receipt | SHA-256 |
| --- | --- |
| Capture | 573aa4aa866a09ef245e27cec49cc0850e4dc7afd9ee5ee82b3f7ad788e88a31 |
| wcprof/workload audit | c90250689ad510473227c2be1e93cd5b78fe18d730ce86f73f8605f5c1eaa781 |
| Kernel attribution | da6a718e041ea65e530656ec594cf095e17ef0c271d329c18709ea639f431d0a |
| Whole-image/process coverage | 81df718b1835044a9593925457f1083b4160e1c27ddf486e4dc89d93b74b6b8f |
| Kernel records, retained locally | 120f11dceb84821a0edf8eef23417d7a88ccd26c52364479a9f561a662114209 |
| Local OTLP, retained locally | 7bb7feba61cb245e1d44864fd0125452a5ec12cd3ee0a2abf14f4065ac48c2be |

Next candidates should improve writeback overlap while retaining final sync,
verification and ownership, and then prove complete-flow gains. No proposal to
turn off device throttling or durability. This 143ms target cannot by itself
remove the 3s image phase or 400–600ms warm tax; the larger paths remain priorities.
