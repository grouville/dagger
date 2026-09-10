# Deferred OAuth startup: first A/B result

2026-09-10, Linux amd64. Nine samples per variant, alternating order, no samples
discarded. Same current-main engine (59a9b904d1), same warmed two-crate workspace,
same rsync/Cargo module. Both CLIs built locally with Go 1.26.6, CGO disabled,
matching version injection and stripped binaries. The baseline uses the parent
branch's llm_config.go via Go's build overlay; the candidate defers OAuth refresh
to the existing env-secret resolution hook. No retained CLI session.

| Command | Baseline median ms | Candidate median ms | Difference ms |
| --- | ---: | ---: | ---: |
| `dagger version` | 230.43 | 65.31 | -165.12 |
| `dagger check rust:check` (exact warm) | 1096.67 | 891.11 | -205.57 |

This environment has expired OpenAI Codex OAuth credentials. Baseline startup
contacts the endpoint and receives HTTP 401 on each invocation. The candidate
does not contact that unrelated provider for these commands. This saving is
conditional on credential state/network latency; it is not a universal 200 ms
speedup, a native-Cargo win, or an edit-path result.

Focused tests verify startup makes no OAuth HTTP request, actual env-secret
resolution still attempts refresh, explicit auth tokens are preserved, and
expiry environment export still works. Existing secret-provider behavior logs
refresh failures and falls back; this change does not modify that policy.

Native wcprof on the preceding source-sync benchmark recorded 140.4 ms for an
exact-check engine span, much less than whole-process wall time. The A/B isolates
one CLI cost outside that recorder. Remaining lifecycle costs still need OTel
and further profiling; these measurements do not close the warm-hit goal.

Binary SHA-256:

- baseline: ccf0b7fea2b17036d8f48bdeac79ead76c713e46c28b484f773ae588a1ca1064
- candidate: 5507e7e555a18847e3a0d2d413651f640d1fe42703f0151af7ae7dad72928248

Raw samples: `oauth-startup-timings.csv`. First-use samples are retained. Results
cover a single machine and real configured credential state; broader auth/LLM
integration tests and representative Rust repositories remain necessary.
