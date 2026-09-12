# Preconnection on real edits, dependencies and fresh engine state

No code change after ca454ac8870db5c9f5d62573f73ecf03a2849464. Three independent
AB/BA/AB pairs with six disposable engine/Cargo stores. Same verified-stream
engine image848 and pinned modulef6/Rust/ripgrep on both sides; only CLI differs.
Both CLIs include the earlier readiness prerequisite and were rebuilt on7c35
main. Engine remains the retained earlier experimental build, not a new complete
latest-main stack. This cohort uses848; preceding exact-only pilot used3df.
Never pool those results or add earlier independent patch savings.

## Results

All times ms. Cargo/Dagger columns are marginal medians; savings are median
matched differences. Repeated warm samples are summarized per run first: three
independent pairs, not nine. Every sample and losing pair remains in the JSON.
Positive savings mean Dagger improved versus its control, not versus Cargo.

| Flow | Cargo | Dagger candidate | CLI paired saving [min,max] | Favorable pairs |
| --- | ---: | ---: | ---: | ---: |
| First check, empty engine store* | 6702.111 | 14090.604 | −443.967 [−1142.932,236.452] | 1/3 |
| Provision + first check* | 6702.111 | 14301.614 | −441.654 [−1169.092,228.996] | 1/3 |
| Exact cached result | 120.742 | 433.027 | 40.145 [30.995,60.752] | 3/3 |
| Application source edit | 289.892 | 816.664 | 50.545 [49.749,88.255] | 3/3 |
| Workspace-library source edit | 454.837 | 971.965 | 60.879 [46.529,86.120] | 3/3 |
| Actual bstr1.12→1.13 upgrade* | 1637.075 | 2151.669 | −34.391 [−56.821,89.619] | 1/3 |
| Unchanged after upgrade | 119.148 | 416.741 | 46.056 [45.066,109.665] | 3/3 |

*First check/upgrade are profiled; other timed flows are unprofiled. Native Cargo
uses docker exec in the matched preinstalled Rust image. Docker, CLIs, engine
image, local module and native image were preinstalled. Engine state, Rust image
inside it, Cargo outputs/dependencies and CLI state start empty per run. Registry
route is explicit direct-origin (no dev-engine mirror), not a claim about every
default environment. Host page/CDN caches were not purged. No complete-install,
artifact/fmt/clippy/test-command, macOS or remote-performance claim.

Remaining median matched Dagger overhead: exact310.100ms, application521.936ms,
library519.149ms, upgrade510.114ms, followup297.163ms. First-check overhead
7508.908ms; provision+first7722.794ms. These are paired-overhead medians, not
subtractions of marginal table medians. Every representative flow still loses
to native; warm overhead remains unacceptable for the goal.

Native-normalized overhead savings are also retained: exact35.073ms,
application66.494ms, library50.539ms, followup49.512ms (all3/3); upgrade5.101ms
(2/3); first210.126ms and provision202.670ms (2/3). These mixed cold/upgrade
normalizations do not erase their user-visible CLI losses.

## What the profiles establish

All36 structural/completeness checks,18 post-timer cache analyses and36 ordinary
warm crate-rebuild audits pass. Cold downloads/unpack read both exact pinned Rust
layers in every run (316873658 compressed bytes); no missing/reduced toolchain.
Ordinary app edits rebuild only ripgrep; library edits rebuild grep-printer,
grep and ripgrep. Actual upgrade selects bstr1.13 on both sides and leaves
unrelated memchr cached. Failure, repair, failing-source revisit and owned-engine
restart/reuse gates pass. Exact and restart-exact diagnostics execute no Cargo.

Warm replay drift −0.0..−0.1%, but **cold replay drift −5.8..−6.5%**. Cold captures
are structurally complete; their simulated causal rankings are not accurate
enough to claim a precise what-if saving. Actual CLI wall times and recorded
span intervals remain observations, not proof of cause.

Cold connection setup is21.629/30.561/40.876ms shorter across pairs, while full
cold CLI is slower in two. The Cargo-action interval is1023.938/−229.560/623.707ms
longer in B. Image-delivery interval changes+23.169/−172.673/+69.306ms. The net
result is not a cold win; the action timing variability has no established cause.
For bstr upgrade, connection setup improves20.173/51.276/22.908ms but the Cargo
action is37.059/36.098/72.166ms longer in B. Preserve this discrepancy rather
than attributing the full action-time difference to a transport change.

Later profiled app diagnostics follow a failed library revisit/cached repair and
correctly rebuild three crates; they are distinct from ordinary timed app edits.
No post-hoc workload/sample replacement or profiler opt-out was used.

## Reproduction and retained evidence

Exact local scripts are fullflow-run.py, fullflow-analyze.py and
fullflow-summarize.py. They retain original paths/pins; use a fresh owner for a
rerun. The controller asserts ca454 source and build hashes, so merely adding
this evidence commit requires selecting the recorded source checkout for an
identical rerun. Changing only that documented source pin after checking that
production hashes are unchanged is a new recorded run, not an overwrite.

```sh
python3 /tmp/dagger-preconnect-flow.xir7YN88/run.py --execute
python3 /tmp/dagger-preconnect-flow.xir7YN88/analyze.py \
  /tmp/dagger-rust-cli-flow-ab-cdgx776g
python3 /tmp/dagger-preconnect-flow.xir7YN88/summarize.py \
  /tmp/dagger-rust-cli-flow-ab-cdgx776g
```

Owner /tmp/dagger-preconnect-flow.xir7YN88; benchmark30770 and analyzer84949
completed0. Summary completed0. Cohort cdgx776g contains the six workspaces,
process boundaries, native/crate diagnostics, wcprof/cache snapshots and engine
logs. The actual fixture directories are listed in fullflow-cleanup.json.
All six owned native/engine containers and cache volumes were independently
verified absent after cleanup. Captures/workspaces remain; retained dev engines
were not stopped. OTLP receiver ended−15 as requested by its controller.

Raw42658432bytes SHA25684cbadc75c19359b8e377bf631085a4d208c320be194c4c99dc3797a4726592f;
fullsummary6dfc2194f9b30972ab4611165496f89e7b3a48c6f4583ffa34efa07d6d695653;
fullreportecf7b2f9df4301209cc5ec841ec9d914d73b5d3e6ad38da5ded15d5c97785f3a.
Published JSON is a compact projection, not those original-byte artifacts.
ControllerSHAca88d62f89d19135a819d0a338274392722584eaa733e9cca38622f185decc44;
analyzer812011e1d5f6d895e242553dc8ad1eeec3834798d641e55afa22e011831e7194;
summarizeraadd2c7b3c0841dae18f560170a6740709660efe4179749867f6fbd3a28b253f.

Next: explain the remaining module/source/session costs with warm wcprof,
validate the complete rebased engine stack and supported integration paths,
and keep addressing toolchain delivery separately. Do not promote this local
result as a solved Rust module, cold start or native-performance replacement.
