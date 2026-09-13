# Local evidence and completed processes

Measured owner: /tmp/dagger-container-inventory.NMh2Z3QV.
Full cohort: /tmp/dagger-rust-cli-autoprovision-ab-krjzd4do.
Publication is a separate clone; measured source/controllers remain frozen.

| Artifact | SHA256 |
|---|---|
| Raw OTLP, 43,404,506 bytes | 8d9ccd79bd7a4b572bd31be858607d35020567df29e94da08e498c4479d45db1 |
| Full summary | c3c08466f76e5837c3e8c208bda6c8aa31714ce1359da793c7ccaa3755cc6070 |
| Phases | 3aff3b37c786bb956df990d873887163b491e0c58710f08978dc5c9b856a1c41 |
| Full driver analysis | 2107173c49aaffcf104340c62d87c7c849e49158903f9617760b4825fddb300b |
| Full wcprof report | 44df7b7423f15252ad1c78633aaa10fa26aaa3d989b7e0aa62cf685fbe71e2fc |
| Ordinary-execution report | 49b8ee0036ed8d885fc0c2f9a93377d942970724f82bc2f25591318f53aa89d4 |
| Build inputs | e617c45618290bbe31555c4f6e5e0ceae86b3756451d9b51d03d55f99e1c80f8 |
| Final measured unit log | 87d72c8e48675f8d9cdd2158ff1310801b17b4f55f4f0437d9c61c507b2db32f |
| Owned Docker contract log | 16e7561df603de231f3eed186c4bb115aeb258475646dc1dda31e99e1106c721 |
| Publication unit log | 9f672d3adc8d724923150dba76323c23f1a57f59a638bcf4cfa2d8db60c4eb0c |

Before-test 25753 completed exit 1, expected missing Docker prefilter in 3/3.
Initial build 63770 and final build 91862 completed exit 0; final binary equals
the initial candidate byte-for-byte. Docker contract 56509 completed exit 0.
Fullflow 51533, analyzer 80664, ordinary audit 11007 and phase/driver/summary
analysis completed exit 0. Publication tests 51695 completed exit 0.

Read every cleanup.json: three removed resources per run, no retained resources
or errors. Independently listed all exact owned container/volume names afterward:
none remain. The four owned contract containers were independently absent too.
Receiver 1852307 exited -15 during normal teardown and was independently absent
(ps exit 1). Temporary resources were removed; fixtures/logs remain locally.

Retained engine stayed container
8ad9acfed0967173292b23ca0fa5dc1070980b3773950ddb74db8746bfbb8ab5,
image 1fb3565bb5bac059d2a89e52e231203befe215ba4396ea40c93393b19f77aeb0.
All 38 recorded binary/source/tool/controller hashes were rechecked after timing.
Publication source and tests match build-inputs.sha256. The shared dirty user
worktrees were not modified.

Published results omit full raw profile details; driver analysis omits raw span
samples. Original full hashes are above. Unrelated inventory names are local-only;
the guarded 58-container inventory digest is
ca7cc3fceefcc9e14c81016c706e12611e9fed0c4b6cf35ee3dcd7a6ec0ffa21.

An initial publication-only compact JSON command was rejected for a missing
closing brace and corrected. No measured data, frozen controller or source
changed; that failure did not trigger a replacement benchmark.

The staged whitespace check flagged testify's literal indentation/trailing spaces
in validation/before.log. That verbatim failing-test output alone is exempted by
validation/.gitattributes; production code and other evidence retain normal
whitespace checks. The original local log remains unchanged.
