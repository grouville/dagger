# Pinned inputs and retained local evidence

Branch base: upstream main `6bf59d50654ce9244ebeee1cc090b7dce3fe3083`,
reverified before publication. The measured frozen experimental source was
`db9d005c715ac9d146780d783faf7f7b55d23e5e` atop that main.

- CLI SHA256: `984c0d2e5e3f22ffb71bf8a9367b4b784120681ebc27923296adbba9817ac227`.
- Engine image: `sha256:3b711dbd1020dc827a3a1e452fba01c480e924cdf6151b623f8214ca5a1abf5d`.
- Original Rust image: `rust@sha256:39f68a3e8e3ff425f8945ffa91128e60ff930d53e17fbb5214e95824bdd46f1b`.
- ripgrep revision: `3fce3b5bb0236da2df6d99672afb8a719642eca7`.
- Base module SHA256: `f6e119c3b7be439df46a6ea9b74c368126751e0a141b2e5ebb699a4b0f0681f1`.
- Prepared module SHA256: `3849571ffad110f00a36f8fec0d2b5b8f0a22d5c3fee02208c4940db18b0f384`.
- wcprof analyzer SHA256: `de3bde25361254d784a211a9fdfec5043459a7a211b9e2a012252ebfbd45a8ba`.

Historical exported manifests:

- Base: `sha256:1f07f720e5bb0e319daac3aa846a75b25d8489db213cf3641867787dd0393c03`.
- Prepared: `sha256:1cff4ff565af866b4d0c9c24da3907906da01a902b9b4074e11004af41171fd4`.

These differ from the original Docker image descriptor because export uses
ordinary OCI metadata; base layer bytes and diffIDs are unchanged. They are
historical descriptors, not published registry references.

## Exact historical local commands

These require the retained experiment directories; they are recorded for
audit, not claimed runnable from a fresh clone of this evidence branch:

```text
python3 /tmp/dagger-rust-toolchain-package.cYaZRS0C/run-pairs.py --execute
python3 /tmp/dagger-rust-toolchain-package.cYaZRS0C/analyze-local-package-v2.py /tmp/dagger-rust-cold-image-ab-6jh2p324
python3 /tmp/dagger-rust-package-confirm.i8tcd5Qe/run-pairs.py --execute
python3 /tmp/dagger-rust-package-confirm.i8tcd5Qe/analyze-local-package.py /tmp/dagger-rust-cold-image-ab-bnqj8wp6
python3 /tmp/dagger-rust-package-confirm.i8tcd5Qe/summarize.py /tmp/dagger-rust-cold-image-ab-bnqj8wp6
python3 /tmp/dagger-rust-package-confirm.i8tcd5Qe/history-summary.py
```

The controllers refuse existing output paths. Repetition needs a new owned
namespace, not deletion of retained evidence. They record exact argv, compiler
and binary/source/config hashes, fresh-state setup, process boundaries, trace
handles and Docker resource identities in `cohort.json` and `processes.jsonl`.
Only test-owned containers, volumes and networks were removed; absences were
verified. No user cache cleanup or public-registry writes occurred.

Original controller SHA256:
`ff0fc951788e1848a1395188b8f930f406bc1038cfd1621995f2d270c53f4b6b`.
Confirmation controller SHA256:
`59ea06598633aaa15b473aa14fbacb43c27b3fb76e9285c5aac0a69ffe88a1aa`.
Confirmation runtime adapter SHA256:
`160fcc9cca40a45078ac1a3ad9073a96ac572911a7a10acc4af00edfc6b1b03f`.
Combined history SHA256:
`594f81095b89396b80dd3234ee881418c7bf77254c1d6d1effce55cfe1913d2b`.
Individual report/summary hashes are also in `measurements.json`.

Original analysis first failed its cold-byte gate due to a shortened display-
name filter. That report remains in its `analysis/`; the corrected full image
name produced `analysis-corrected/` without rerunning the workload or relaxing
gates. Confirmation used the corrected filter from the outset.

HTTP diagnostic evidence is retained at
`/tmp/dagger-rust-cargo-http.7697tBox/RESULTS.md`, cohort
`/tmp/dagger-rust-cold-image-ab-n777h7zi`. Its allowlisted summary SHA256 is
`78a1bceb832f302522fe401ff14c3e545a7b07e47ea3dde89786f3b1b80a5053`.
No raw HTTP log, credential, private profiling executable or telemetry corpus
is included in this branch.

Published helper validation: sources/logs at
`/tmp/dagger-rust-package-publish.opKf02fB`, new exports at
`/tmp/dagger-rust-package-export-check.5RYANDrt`. `export-validation.log` retains
the normal SDK session run and warnings. `builder-argument-tests.log` records
the three rejection cases. Both exported archive hashes equal the historical
artifacts, as recorded in RESULTS.md. No user worktree/caches were reset.
