# Separate first-call phase diagnostics

Prepared only. The parent must grant a runtime slot after source review. This
uses exactly two new empty Dagger volumes, one original Go/base and one optional
baseAddress, with the same engine `38711bd2`, CLI `d6858098`, image, ordinary init and
SDK blobs as the completed four ordinary observations. No build or preparatory
image pull is added. The sole Dagger command on each volume is
`--profile check -l --all`, with the same exact ordered 14 output gate.

These are instrumented diagnostics and must not enter the ordinary timing
summary. The bounded engine wcprof dump is fetched after full CLI exit; there
is no pre-run dump or primer. The purpose is to separate cold source/SDK/schema
registration, backend constructor/function processes and collection expansion,
using operation counts, interval union and critical-path enclosure rather than
summing overlapping spans. HTTP payload/body data and raw profiles remain
private. Numeric reduction must retain open/dropped operation counts and note
that process CPU totals do not by themselves identify compiler work.

The reviewed cold lifecycle is reused with a distinct owner label and container
prefix, two-call cap, 300-second CLI limit, 8 GiB sampled engine writes and 16 GiB free
floor. Only newly owned containers/volumes are involved. Provisioning/start,
profile capture and cleanup remain outside the CLI timer. Containers are stopped
and removed; volumes are initially preserved and removed only via the explicit
ownership-checked cleanup command after evidence capture. The original fixture
and copied authored files must remain/restored exact. Any first failure aborts;
there is no automatic retry or extra Dagger query.
