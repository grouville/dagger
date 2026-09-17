# External compilation during this comparison

This cohort is not a uniformly idle-host performance comparison. Its raw
captures, source/correctness gates and outliers remain unchanged.

During round 5's asynchronous arm (runtime-r72), a read-only process snapshot
showed several active `rustc`, `clippy-driver` and `cc1` processes. The user
confirmed this was their parallel experiment and canceled it. Around
2026-09-17 05:51 UTC, the subsequent process snapshot no longer showed those
compilers among the active processes. This identifies observed contention;
it does not establish its exact start time or prove earlier samples were idle.

An example retained outlier is runtime-r72/revert: CLI 2325.551 ms, engine
850.648 ms, sync 729.224 ms, no materialization and no background admission.
CPU PSI avg10 rose from 8.54 to 21.49 during that capture. The same round's
later mixed/reorganization captures are also retained, not surgically removed
from the aggregate. Main's round-4 edit/I/O-pressure outlier is retained too.

The full n=6 table remains useful as a diagnostic record, not a clean-host
causal estimate of small asynchronous-admission gains. Disclose this before
the table and require a separately recorded quiet-host confirmation for
production performance claims. Native-profile replay, input parity and output
readback success do not by themselves rule out external resource contention.
