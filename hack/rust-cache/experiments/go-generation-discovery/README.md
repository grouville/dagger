# Go generation-discovery evidence

The selected change shares generation-pattern matches locally inside package discovery. See the [report](../../NATIVE_GO_GENERATION_MATCHES.md) and [review description](../../PR_GO_GENERATION_MATCHES.md). The source is pushed as [511d381](https://github.com/grouville/go/commit/511d38145daf87b531e44ed9b1c3b641fbe89ba3), a follow-up on `de633b12ed2aa02e42adb698a23fcecc13faf36d`. No PR is open.

`assessment.json` contains the final complete-command comparison, all small-repository cohorts, functional gates and profile counts. `final-state.json` verifies all nine retained engine binaries and volumes, restored workspaces, idle runtimes and disabled capture switches.

The archive retains four separate studies:

| Directory | Purpose | Decision |
| --- | --- | --- |
| `native-sort/` | Replace three interpreted sort helpers using the development builtin | Unselected: small, variable command-level differences |
| `source-labels/` | Attribute reduction CPU by authored source location | Diagnostic only; dedicated engine and interpreter race suite |
| `shared-api/` | Share generation matching through a new `gomod` call | Unselected: all small-repository pairs regress |
| `local-discovery/` | Reuse immutable matches in the existing discovery invocation | Selected: all eight real-repository pairs improve; small timings remain mixed |

Each study includes its scripts, all attempts, exact module identity, raw timings, stdout/stderr, source restoration records and available profiles. The API variant retains its initial test-fixture edit failure and corrected success. The final implementation adds a different discovery regression that passes baseline and candidate.

`module-source/` contains tracked source snapshots and diffs from the common base. `module-identities.json` records their commits and file hashes. The selected production and regression patch is also available as `module.patch`.

The benchmark engine is unchanged from the sealed-metadata study. `engine-source-parent.json` identifies that source archive by hash; its own parent references remain necessary. `diagnostic-source-delta.json` verifies that the dedicated diagnostic differs only in the reduction-label wrapper. That engine retains `DANG_PROFILE_LIST_REDUCTIONS=true` and is never used for latency comparisons. Its CPU and wcprof capture switches are off after recording.

`manifest.json` identifies every archive member; all hashes were checked after compression. `archive.json` identifies the archive. Fourteen wcprof streams are retained as gzip chunks. Their exact reconstructed hashes and event counts are recorded in `wcprof-reconstruction.json`; `local-discovery/archive.py` shows verification and reconstruction. Executable binaries and duplicate uncompressed streams are excluded.

Warm measurements do not establish current cold, stock-engine or Rust performance. The cohorts use different states and must not be added together.
