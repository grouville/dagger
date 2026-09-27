# Smaller PID1: validated prototype and bounded startup measurement

The focused normal/race gates and real PID1 orphan-reaping test pass. A bounded
host process-startup experiment supports continuing to full Dagger validation:
heavy init median **10.019 ms**, lightweight init **1.471 ms**, with a median
paired reduction of **8.744 ms** over twelve alternating pairs.

This is not a whole-CLI performance result. Both executables received an
unmatched argv[0] and exited before either PID1 or attachables mode ran. The
measurement includes host process creation through blocking wait4 completion;
it uses warmed host caches, GOMAXPROCS=4, four excluded primers, no engine, and
no Cloud. A joining waiter records actual exit completion, with an owned-child
timeout/kill path. All thirty child processes completed successfully.

| Ordinary startup, n=12 each | Heavy | Light |
| --- | ---: | ---: |
| Median wall time | 10.019 ms | 1.471 ms |
| Observed wall range | 8.288–16.255 ms | 1.215–2.240 ms |
| Median user CPU | 8.737 ms | 0 ms |
| Median system CPU | 5.520 ms | 1.369 ms |
| Built binary size | 47,972,514 B | 1,945,762 B |

Separate `GODEBUG=inittrace=1` captures reported 505 versus 19 initialization
records, 3,402,416 versus 1,728 allocated bytes, and 21,629 versus 30 allocations
inside reported package initialization. Those diagnostic runs took 26.986 and
2.040 ms and are excluded from ordinary timings. Their reported clock sums are
not substitutes for ordinary timings. Raw inittrace output remains private;
the archive contains only counts, sums and hashes. Process ru_maxrss is retained
as a raw counter but not interpreted as Go heap size or a memory improvement:
both child high-water counters can include the fork/exec launcher's earlier
address-space footprint.

The saved 58/67 ms pre-query intervals remain broad startup bounds. These
measurements do not assign the remaining gap to runc, attachable setup, SDK
startup or nested admission, nor predict a saving across several module calls.

Validation provenance:

- `validation-v1` stopped before compilation because the sandbox could not
  write the existing Go build cache.
- `validation-v2` stopped at vet because the overlay-only new package had no
  physical working directory; `validation-v3` confirmed the test runner also
  needed that directory. Neither attempt executed semantic tests.
- `validation-v4` used an authorized empty package directory and normal vet.
  Both packages passed normal and race gates, with twelve reported parent/test
  cases per mode. The privileged PID1 case was explicitly skipped there.
- `privileged-gate-v1` then ran that case successfully, without a skip, in one
  task-owned privileged container with network=none, no host PID namespace,
  read-only rootfs, only its test binary bind-mounted read-only, and tmpfs /tmp.
  The owned container and empty overlay directory were removed afterward.

Build provenance: HEAD `0d1c32e29f`, frozen ec6 experimental SDK/engine overlay
and exact dependency modfile retained in both arms. Matched engines are
`cde14615…` / `48fc8d7d…`. **Both arms must use the same newly compiled heavy
helper `e5157dc9…`**; the light binary is `fa267a45…`. Comparing an existing image
helper against a newly built helper would add a confound. Both helpers must be
packaged alongside the selected engine; replacing the engine alone is invalid.

The production candidate preserves the original PID1 body byte-for-byte and
keeps attachables/providers in a separate process. It does not add a source or
result cache, change module authority, or bypass declared inputs. It adds a
read-only helper mount, whose cost and extra reserved container path must be
included in actual Dagger testing. The prototype duplicates the PID1 body to
make its parity auditable; an upstream version should share the lightweight
implementation without importing heavy providers into the light command.

Remaining gates: real nested Go/TypeScript/Python dispatch, fresh unique inputs
that force execution, normal exec/NoInit/service behavior, platform packaging,
TTY behavior and complete CLI exit timing. This remains an isolated prototype;
it has not been applied to production source or claimed as a 500 ms result.
