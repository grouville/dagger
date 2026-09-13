# Retained local evidence

Source owner: /tmp/dagger-cli-readiness-current.AS6z1ng4.
CLI-managed cohort owner: /tmp/dagger-cli-readiness-auto.C70FUvMf.
Publication uses a separate clone so measured source/controllers remain frozen.

The publication clone independently passed the exact focused race selection
(`go test -mod=readonly -race -count=3 -run '^TestWait' ./internal/buildkit/client`)
in 6.151s, terminal exit 0. Its production/test files match measured build inputs.
The retained validation/publication.log SHA256 is
aabedf830502a89314c4ece96595d99a26025327645d2b31c25c77c2cb117634.

| Local artifact | SHA256 |
|---|---|
| Manual raw OTLP, 42,601,589 bytes | 49a0926c992137ed9faaf698ddf7b128a52f09e2a1cef45d204801630b55e57a |
| Manual full summary | 2cacc1808198dfc29e8e3f1785df27201595597f129eacca4867c4477ab35a4c |
| Manual phases | 3971a7310af9d4f96d68d7961beae70456ecb635430a1d3e390e46bc1e857634 |
| Manual full wcprof report | 63155b599a1323c8d5a0e4f1236f4ffe363e8fe0dd74f02808bcc761a49c7a83 |
| Manual ordinary-execution report | bdf19b5713d17ee55dfa8d8c7d173d12d79cfda88da81b3867fbf7d37c01fe86 |
| CLI-managed raw OTLP, 43,564,403 bytes | 58f98a8249e8b67280dc999ea99084ec79f1eb95292d45aea7ac01c5e173801d |
| CLI-managed full summary | 3ae7ba911ad17abbc8f92d1cda1474ed7287ab9765166dac2fa49cc7c33b57aa |
| CLI-managed phases | a9a3b6193f13bf1d7f7db4c70c2a9f4ddaa840dbbbe4f3ed72cea9f981f371e1 |
| CLI-managed full driver breakdown | c7fae6869e3fcc37811572a504c566095a06a7d1b9c67f363c61627643d563fd |
| CLI-managed full wcprof report | 30fa045a9f9e37bcea896ba194976e2941f9855697f3c86351efd41bc1c355fb |
| CLI-managed ordinary-execution report | b9116494678b11bdc37eac07af64c42bfffc6e5812a356fe8f02dac0241dee04 |

Manual fullflow 5355, analyzer 8344 and ordinary audit 93734 completed exit 0.
CLI-managed fullflow 39562, analyzer 66584 and ordinary audit 63865 completed
exit 0. Both phase/summary gates and the derived driver breakdown completed
exit 0; all completeness/count/byte/crate flags were read independently.

Each of the six CLI-managed cleanup.json records has no errors or retained
resources. Independent Docker listing of all exact native/engine names and
volume names returned empty. The earlier labeled manual groups were also
independently absent. Receivers exited -15 during normal teardown; CLI-managed
receiver PID 1679572 was independently absent (ps exit 1). Workspaces, logs and
failed/positive tests remain available locally.

The retained engine remained container
8ad9acfed0967173292b23ca0fa5dc1070980b3773950ddb74db8746bfbb8ab5,
image 1fb3565bb5bac059d2a89e52e231203befe215ba4396ea40c93393b19f77aeb0.
All capture-recorded CLI/source/tool/controller hashes were rechecked after
measurement. Publication's production and test files match build-inputs.sha256
exactly. Shared dirty user worktrees were untouched.

The manual phase analyzer used statusDescription instead of statusMsg when
copying error descriptions. That cohort has no Info errors; numeric boundaries
and gates are unaffected. The original script/results are preserved. The
CLI-managed copy corrects the field before capture; raw records are unchanged.

The 50.028-second candidate cold point is not removed or normalized away:
Cargo emits index-update output at 1789271569169691587ns, a zero-byte/30-second
low-speed retry warning at 1789271599269700465ns, then download output at
1789271600401154158ns. The actual Cargo process span is 37.065 seconds. These
timestamps support localization, not a claim that all future networking delays
are outside Dagger's responsibility.

Published compact results omit full profile details and raw telemetry; full
original hashes are above. Validation logs are local unit-test output, not raw
wcprof traces. Private analyzers, binaries and OCI images are not published.
