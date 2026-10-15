from pathlib import Path
import json
import re

base=Path('/tmp/rust-cache-sipsma-review')
report=Path('/home/dagger/dagger_otra/hack/rust-cache/NATIVE_COMPACT_SCALAR_RESTORE.md')
component=json.loads((base/'scalar-array-restore-components-with-save/summary.json').read_text())

def heap(label):
    root=base/('scalar-array-restore-memory-'+label)
    text=(root/'after-gc-inuse_space-flat.txt').read_text()
    match=re.search(r'of ([\d.]+)(MB|GB) total',text);memory=float(match[1])*(1024 if match[2]=='GB' else 1)
    text=(root/'after-gc-inuse_objects-flat.txt').read_text();objects=int(re.search(r'of (\d+) total',text)[1])
    return memory,objects

micro=['| Operation | Values / call arguments | Main | Compact | Main / compact allocated bytes | Main / compact allocations |','| --- | ---: | ---: | ---: | ---: | ---: |']
for phase,sizes in component.items():
    for size,row in sizes.items():
        old,new=row['main'],row['new']
        micro.append(f"| {phase} | {size} / {size} | {old['nanoseconds']/1e6:.3f} ms | {new['nanoseconds']/1e6:.3f} ms | {old['bytes']:,.0f} / {new['bytes']:,.0f} | {old['allocations']:,.0f} / {new['allocations']:,.0f} |")
memory=['| Reload | Sampled retained heap | Sampled live objects |','| --- | ---: | ---: |']
for label,description in [('main','V1 legacy reader'),('compact','V2 compact reader'),('v2-main','Same V2 binary, legacy reader again')]:
    byte,count=heap(label);memory.append(f'| {description} | {byte:,.0f} MiB | {count/1e6:.2f} million |')
command=['| Process cohort | Listing: Dagger / Cargo | Edited check: Dagger / Cargo |','| --- | ---: | ---: |']
for label,title in [('main','V1 control'),('compact','V2 compact'),('v2-main','V2 control confirmation')]:
    data=json.loads((base/('scalar-array-restore-'+label+'-commands')/'summary.json').read_text())
    command.append(f"| {title} | {data['large_list']['dagger']:.3f} / {data['large_list']['cargo']:.3f} s | {data['large_leaf']['dagger']:.3f} / {data['large_leaf']['cargo']:.3f} s |")
only=['| Check-only cohort | Dagger median | Cargo median |','| --- | ---: | ---: |']
for label,title in [('v2-main-check-only','V2 legacy reader'),('v2-compact-check-only','V2 compact reader')]:
    path=base/('scalar-array-restore-'+label)/'summary.json'
    if path.exists():
        data=json.loads(path.read_text())['large_leaf'];only.append(f"| {title} | {data['dagger']:.3f} s | {data['cargo']:.3f} s |")
    else:only.append(f'| {title} | In progress | In progress |')
text='''# Keep restored builtin scalar lists compact

The [standalone engine change](https://github.com/grouville/dagger/compare/a5c17bb7e...376e7c324) removes repeated call copies when loading plain scalar lists from cache. On the accumulated benchmark engine, switching the same final binary between readers changes retained sampled heap from **5.2 to 2.8 GiB** and live objects from **33.2 to 15.5 million**. Native compiler results remain reusable. No PR is open. The native Rust edited-command latency target remains unmet.

## Change and correctness

The old reader creates a detached result and deep-copies the producing call for every inline scalar. A list of N values whose call contains M arguments therefore does O(N×M) call-copy work. The new representation keeps plain scalar values and one independent recorded call; an element's result is created when requested. Reading the array takes O(N+M) call-copy work, in addition to parsing its scalar payloads.

Only non-null builtin scalar elements without attached identities, resources or offers qualify. Nullable, custom, referenced and resource-bearing elements keep the general decoder. Invalid payloads retain its validation and error messages. The new representation preserves the recorded element calls even if a consumer supplies no call or another one, and it retains independent call ownership. It reuses `DynamicArrayOutput` value serialization and field assignment. The private in-memory representation changes; one existing nested-list test now uses `Enumerable` for its plain leaf while preserving value/identity assertions.

Saving the new representation reads plain values directly; otherwise it would recreate the expensive calls at shutdown. Snapshot-owner traversal also skips these closed builtin values. There is no new lock, dependency, global production cache, diagnostic flag or persistence format. The existing version-5 envelopes are unchanged.

The full `dagql` package passes under `-race` after both restore and save changes (67.727 s). Regressions cover exact values and large numbers, element call identity, ownership after caller/child mutation, nil-frame access, assignment, bounds, repeated restores, identical saved envelopes, invalid versions/payloads and per-item session resources. Existing tests cover nullable/custom values, references, nested lists, transfers, owners and pruning. A production-source search found the other core uses construct result-backed arrays; the representation assertions in snapshot tests concern object arrays, which retain the old decoder.

The real engine preserves all six native histories before and after edited workloads and after switching back to its legacy reader: both histories reuse 130/130, 1,026/1,026 and 6/6 compiler actions. The legacy reader successfully loads data saved by the compact implementation. Artifacts and incremental state remain native Dagger snapshots.

## Component and retained-memory measurements

Five fresh-process pairs use Go 1.26.6, GOMAXPROCS=8, rotating order, fixed quiet admission and 300 ms per benchmark. The comparison overlays the unmodified main decoder and owner walker. Each fixture has N strings and N literal path arguments; this deliberately exercises the observed repeated-copy shape. Save timing starts from an already-restored value. These are construction/allocation results, not Rust-command speedups.

'''+ '\n'.join(micro)+'''

Heap captures run outside latency intervals, without active clients and after diagnostic Go collection. The engine has no Docker memory limit. The same persisted volume survives every graceful restart; its dataset can grow or compact, so the reversal and allocation stacks matter more than treating the snapshots as an exact census. These are sampled Go heap estimates from a long-lived experimental cache, not a claim about a normal project or a leak.

'''+ '\n'.join(memory)+'''

The same-V2 reversal is about 47% fewer retained bytes and 53% fewer objects with compact reading. In the legacy reader, detached scalar results and cloned calls account for about 2.4 GiB cumulatively. That expansion disappears from the main retained allocation stacks in compact mode; scalar-array decoding retains about 104 MiB cumulatively. Frames overlap and must not be added.

## Complete edited commands

Each process gets two warm-up passes followed by eight admitted measurements per workload. Every invocation edits a used Rust value. The CLI, Rust module `cd6d25e`, source history, compiler image, telemetry and native cache key are unchanged. Listings must contain the exact 1,026 package names. Cargo uses Rust 1.77.2, incremental compilation, eight workers and locked/offline workspace checks. Batch telemetry metadata reuse and the selected attribute decoder stay on; direct span-protobuf conversion, source-import snapshot seeds and snapshot notifications stay off. Wcprof and diagnostic counters are off during timing.

Admission requires an idle engine, a one-second quiet window, host/engine I/O stalls below 5%/1%, host CPU stall below 10%, engine CPU below 0.05 CPU-seconds/second, and a maximum wait of 60 seconds. Admitted observations are never filtered afterward. These are separate process cohorts, not paired old/new command measurements. The first V1 control predates completion of saving the new representation; its disabled path does not construct that representation. The subsequent two cohorts use the same final V2 binary.

'''+ '\n'.join(command)+'''

CPU charged to the engine during listing increases from 12.05/13.09 seconds in the two controls to 16.28 seconds in compact mode; the following check decreases from 3.66/3.85 to 1.77 CPU-seconds. Those counters exclude later background work. That difference motivated additional cohorts of edited checks without interleaved listings. It does not by itself identify the cause or prove faster compilation:

'''+ '\n'.join(only)+'''

The isolated checks do not confirm the apparent improvement in the mixed cohorts: 2.225 versus 2.281 seconds for Dagger while Cargo changes from 1.153 to 0.922 seconds. Across admitted samples, maximum host/engine I/O stalls are 34.2%/1.1% in the initial control, 2.0%/0.2% in compact mode, and 4.7%/0.2% in the same-binary control. Check-only host maxima are 9.1% and 8.0%. All observations remain included. The 10.8-second compact warm-up is retained in the logs and excluded from the fixed eight-sample measured cohort like every warm-up.

## Remaining hot path

A separate fresh edited check takes 1.875 diagnostic seconds. Its complete wcprof capture has 10,830 events, zero dropped events and zero open operations. The longest query takes 1.68 seconds: source import uses about 405 ms, package discovery's invocation about 200 ms and Check.sync about 979 ms. The invocation includes compiler/helper work and API waits, not interpreter CPU alone. These durations describe one capture and are not additional benchmark observations.

The accompanying ten-second Go CPU profile includes 4.91 sampled CPU-seconds, with 2.87 cumulatively in engine cache pruning after session completion, including size accounting. This includes work after the command; it must not be added to the command's elapsed time or confused with Go runtime GC. Repeated cache accounting is a concrete next investigation. The earlier [sparse usage-map allocation change](CACHE_USAGE_ALLOCATIONS.md) is still not installed in this engine. Source import and compiler/helper preparation remain the next latency work; the [native source-import snapshot experiment](NATIVE_SOURCE_IMPORT_SNAPSHOTS.md) still needs its storage/transfer checks.

Memory and decoder-construction improvements are established on these fixtures. Complete-command latency remains sensitive to workload order and host conditions; Cargo itself varies across cohorts. No general edited-command speedup is claimed. The native-Cargo-plus-0.5-second target is still unmet. Registry dependencies, general build scripts, procedural macros and remote automatic state discovery remain separate unfinished work for the native backend.

[Raw samples, admission/pressure records, test logs, local harnesses, exact source manifests and heap profiles](experiments/compact-scalar-restore/).
'''
report.write_text(text)
print('Wrote complete data-derived report for restore/save, memory and all five command cohorts.')
