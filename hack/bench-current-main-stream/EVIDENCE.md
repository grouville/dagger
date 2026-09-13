# Local evidence and cleanup record

Measured owner: /tmp/dagger-stream-close-order.6U5EYNjb

Cohort: /tmp/dagger-rust-current-stream-ab-w77v4f4q

All timed/source artifacts remain unchanged. This branch includes compact
derived results and validated source patches, not raw traces or private tools.

| Artifact | SHA256 |
|---|---|
| Raw OTLP, 42690953 bytes | fb575b360e90089c6c541a4790556c58bce2ccb84c30655091f0e42d795752cd |
| Full local summary.json | 97f87d4b76c5ba9d11a182793d63caf4b5ad2ee7c7f4e0a4e7bbcabfe846ccc6 |
| phases.json | a0f2ab6c423b4be5ae6d32485c77babbdc3f0221224f217609df11d00de0f7e2 |
| Full analysis-r2/report.json | f40cc32e29f162f2e6d414608d4f3c64245f455259612a66b4cc334366c4e4f6 |
| Full ordinary-exec-audit/report.json | 5bfba73fe2f4587d19fb953a5e4ee528b236fb97b9d49839f3c13222657d9062 |
| Frozen run-fullflow.py | ee640463455e45ef6d24c47a648902c28e0e5cc1b8ce27b06e38b8a6d16c5227 |
| Maintained wcprof executable | de3bde25361254d784a211a9fdfec5043459a7a211b9e2a012252ebfbd45a8ba |
| CLI, both treatments | ff1ef25902a037b41e8b16372fcdb806c0cffdd1568a0b9ed75b4e1ef1631f51 |
| Original module main.dang | f6e119c3b7be439df46a6ea9b74c368126751e0a141b2e5ebb699a4b0f0681f1 |

Fullflow session86673, analyzer13465 and ordinary audit10099 all completed with
exit0. Summary and phase/overlap gates also completed with exit0. Both the full
analysis all_captures_pass flag and all54ordinary checks were independently read
and required, not inferred from analyzer exit status.

Independent post-run Docker ps and volume ls filtered on dagger.rust-bench both
returned no resources. This includes all six unique fixture groups in
capture-manifest.json. Their workspaces, logs and captures remain recoverable in
the cohort's recorded roots. Only disposable containers/cache volumes were removed.

Retained build engine identities match the build manifest after cleanup:

- A container6e46d6e050577f38fd06d7f31c505a0fb811c1e0047b62914d117dc7ed4c504a,
  image61caf070e71090c43167e1e2dbb4477efbf47ee170f8da523df2632fc4e65dfc.
- B container8ad9acfed0967173292b23ca0fa5dc1070980b3773950ddb74db8746bfbb8ab5,
  image1fb3565bb5bac059d2a89e52e231203befe215ba4396ea40c93393b19f77aeb0.

The receiver exited with -15 during normal controller teardown and its PID was
independently absent. All build-recorded changed/dependency source hashes and
capture-recorded source/tool/controller hashes were rechecked with sha256sum
after timing. Shared dirty user worktrees were not changed by this experiment.

Patch reconstruction in /tmp/dagger-current-stream-patch-check-abjfg_nm passed:
all26candidate files exactly match the measured hashes, and reversing/reapplying
the isolated close-order patch reproduces the negative/positive dependency hashes.
The verifier uses a fresh owned temporary directory and edits no input checkout.
Literal patch context contains required leading spaces before Go indentation;
the non-patch git whitespace check excludes those three artifacts. The verifier
separately applies them with strict added-source whitespace validation.
