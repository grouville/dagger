The standalone two-line fix and regression are on `fix/class-fork-history-isolation`, based on upstream `18d51f8291eabe93dc2b8e93dd47c8cfa6397625`. The source is pushed to the fork for review; no PR is opened.

[Description](../../PR_CLASS_FORK_HISTORY_ISOLATION.md). [Exact patch](change.patch). `regression-before.log.gz` fails on the original source with the parent reading the fork override; `regression-after-race.log` passes on the standalone fix. `source-identity.json` records both commands, source hashes and scope. The original measured objects.go is byte-for-byte identical to fresh upstream main. The initial offline dependency error is retained separately; fetching the newly pinned dependency resolved it.

This tests metadata isolation directly through Class APIs, covering both Install and Extend. It does not establish an observed production failure, cache miss or listing performance effect. The append-capacity change may add allocation during override installation, with no new read-side work or locks.

Failing test logs are gzip-compressed to preserve their exact whitespace; `log-manifest.json` verifies the decompressed byte digests.
