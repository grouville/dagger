# Index module ownership without changing collection getters

This screen remains unselected. Complete test-edited listing changes **10.73 → 10.59 seconds median**, faster in three of four pairs. Ordinary-source listing stays flat at **6.37 → 6.37 seconds**, faster in two pairs. The small, inconsistent command-level benefit does not justify the added state and explicit constructor.

| Complete-command measure | Scan all module owners | Index owners by path |
| --- | ---: | ---: |
| Test-file edit | 10.73 s | 10.59 s |
| Ordinary-source edit | 6.37 s | 6.37 s |
| Test-file edit, engine CPU | 58.07 CPU-s | 57.22 CPU-s |
| Test-file edit, allocated bytes | 13.62 GB | 13.31 GB |
| Ordinary-source edit, engine CPU | 28.51 CPU-s | 29.51 CPU-s |

The command is `dagger check --module go --check test --list --all` on dagger/dagger commit `ff0b029a4d270a651b9a8c7286babc79089066e4`. Both arms use the same engine and CLI, with prepared-schema reuse enabled and shared receiver decoding disabled. Each invocation starts a fresh CLI and makes a real source edit on the warm engine. Test-edit commands also change a test-file comment. Both arms complete the test addition and removal before four balanced measured pairs per workload. All 24 commands return correct ordered names and identical full rows, and exit successfully. Telemetry, ordinary GC, final log flushing and cleanup are included; profiling and other heavy work are absent during timing.

The baseline getter reduces all discovered module roots to find the deepest owner, then searches the owner list. The candidate builds a private map with balanced merges, walks path ancestors, and retrieves the matching module directly. This makes ownership lookup depend on path depth instead of module count. The authored getter, source snapshots, selection, downstream discovery cache, initialization and test execution remain. Maps cannot be public GraphQL constructor inputs, so the candidate adds an explicit constructor accepting the existing owner list and building the private index. No engine code or lock changes are involved.

The full pipeline still contains repeated work. Lossless wcprof captures retain **804 evaluations, 1,494 SDK requests and all 800 authored getters** in both arms. Test discovery executes once and hits 799 times in each. Getter receiver JSON is **81.382 MB → 81.374 MB**. Converted values fall from 1.956 million to 1.891 million, but converted objects increase from 64,800 to 65,600. Reconstructing every owner's state for every package remains proportional to packages times modules. The index improves the search inside that work; it does not remove the larger repeated preparation.

Eight focused checks pass: existing collection selection, discovery, source snapshots, module-layout rebinding, test execution, binaries and generation, plus ownership coverage for root and nested modules, similarly prefixed paths, spaces, Unicode, exclusions and real nested test execution. Initial constructor and fixture mistakes are retained as failed attempts; they are not attributed to engine bugs. The final fixture keeps excluded test packages discoverable through generation markers, matching the module's existing rule that collections contain packages with work to do.

The engine cache includes a partial import from the earlier cancelled Rust fixture attempt. This paired comparison uses that same retained engine for both arms; its numbers must not be combined with earlier cohorts. No engine or cache is reset. All diagnostic flags are restored, all four retained engine binaries are unchanged, and no client remains active. Cold and Rust latency effects are unmeasured. No PR is opened.

[Sources, patch, every attempt, measurements and profiles](experiments/go-module-owner-index/). The existing [schema-reuse improvement and broader Go/Rust pipeline validation](NATIVE_DANG_PREPARED_SCHEMA.md) remain separate. The next structural candidate must reduce repeated setup and receiver reconstruction while keeping normal per-key getter execution and state.
