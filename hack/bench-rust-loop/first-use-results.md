# Empty-engine first use, 2026-09-10

Pinned ripgrep; CLI with deferred OAuth refresh; rsync source reconciliation;
fresh engine volume and XDG config/cache/data/state directories. Engine image
sha256:c5f729bfc143414d74c17de37fe73b42d335aceaf2cecbf294587b6d6ef103d7.
The CLI, engine image, local module source, native Rust image and Docker already
exist. This does NOT measure the complete new-user installation journey.

The first unprofiled trial measured 34.49 s for Dagger's first check, 6.61 s for
native's first check and 146 ms for native's existing-cache check. Its later
profile-drain step failed because no recorder had yet been initialized. Cleanup
ran. The harness now accepts that specific pre-capture 503, not failed captures.
That trial started native compilation between engine start and first Dagger use;
do not use its phase sum as a precise provisioning/readiness measurement.

The corrected, separate profiled trial runs Dagger immediately after provisioning:

| Phase | Milliseconds |
| --- | ---: |
| Engine container/volume provisioning | 235.28 |
| First Dagger check | 34374.42 |
| Provisioning through first check (continuous timer) | 34622.53 |
| Native first check | 5645.16 |
| Native existing-cache check | 102.26 |

Native wcprof: 31.77 s recorded span, 637 ops, no open ops, no dropped events.
Important durations (nested rows must not be summed indiscriminately):

- Container.from resolver: 2.10 s.
- Container.from lazy image materialization: 19.87 s.
- apt update/install rsync command: 3.08 s.
- rsync plus Cargo command: 6.26 s.
- ModuleSource.asModule: 151 ms self.

This identifies image delivery/materialization and runtime tool installation as
the first-use priorities. It does not prove how much any proposed optimization
will save; image materialization needs finer download/unpack/import attribution.
The one-second onboarding-overhead goal is clearly not met.

The same disposable trial then completed two samples per warm scenario and all
failure/repair/revisit checks. Its engine container and volume were deleted; the
ordinary dev engine and existing caches were untouched. Complete local evidence
is retained at /tmp/dagger-rust-loop-n01bca_f, including first-check.wcprof,
first-use.json, timings.csv, and engine.log. Repeat with a new disposable volume
for each cold trial; do not reset it between edits.
