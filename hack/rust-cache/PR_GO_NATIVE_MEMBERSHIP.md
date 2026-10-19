# perf(go): use native membership for generation directories

Generation-directory selection calls an interpreted equality callback for each candidate path. One real dagger/dagger listing performs 94,232 of these calls.

Use the existing `List.contains` operation for the include and exclude lists. It uses the same string-equality implementation, preserves the existing globs and selection rules, and changes two lines. No engine change or cache is needed.

Complete listing on real dagger/dagger, with a fresh CLI and a warm development engine:

| Edit | Before | After | Faster pairs |
| --- | ---: | ---: | ---: |
| Test file | 7.63 s | 7.44 s | 6/8 |
| Ordinary source | 4.40 s | 4.17 s | 3/4 |

Test-edit timing uses a fixed eight-pair follow-up after the first four-pair screen varied against earlier baselines. Its median paired saving is 111 ms; one slower candidate outlier remains in the evidence. Ordinary-source timing uses four pairs. Both cohorts remain in the evidence. Timings include telemetry, output and successful cleanup. All 44 real-repository commands across the four-pair screen, eight-pair follow-up and ordinary-source cohort return matching rows. Profiles retain all 800 authored getters and the existing per-package discovery hits. The 27 Go checks and 44 one-/sixteen-module timing commands pass, including generation exclusions, edits, selected execution and workspace restoration.

The sixteen-module control is mixed: the initial cohort is 0.746 → 0.893 s (2/4 faster pairs), while a fixed follow-up is 0.744 → 0.694 s (5/8). Natural GC boundaries are uneven across arms; this does not establish a uniform small-repository gain.

This follows the discovery prototype at `511d381`; current upstream, cold and Rust timings remain unmeasured. [Source and complete evidence](NATIVE_GO_DIRECTORY_MEMBERSHIP.md).
