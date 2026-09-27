# Prepared module-owned base Address timing comparison

No runtime has been executed by this driver. The driver cannot freeze or launch until the preceding nine-command correctness proof and its engine/fixture restoration pass.

The experiment keeps one patched Address engine, ordinary init, original CLI, retained volume and workspace path fixed. Both arms load the Go module from the same local directory and the same pinned `gomod@1784ff37...` dependency. The control uses the original module and `base = "dag://backend/go-test-base"`; the candidate uses the prepared module and opt-in `baseAddress` setting. This is an authored API choice: errors from producing the execution container move to use. It is not transparent caching of an eager Container argument.

The exact 28 commands are four ABBA blocks of six commands (one exact checks primer, two unchanged checks listings, two first-seen `main.go` comment listings, one expanded artifact listing), followed by one ordinary checks primer and one profiled identical checks listing per arm. Ordinary checks and edits have four samples per arm; artifact listings have two. The blocks are correlated observations rather than independent randomized pairs. The artifact observations follow a checks primer and have no additional artifact-specific primer.

Both check listing variants must retain the exact fourteen ordered rows. Artifact listings must retain the full ordered, whitespace-normalized control output, including descriptions; no row is filtered to manufacture parity. The new `baseAddress: Address` field is optional, and `walkArtifactNodes` excludes optional values before visiting them, so source inspection predicts no additional artifact row. Any unexpected output delta stops the experiment.

Every edit has a fresh UUID-based comment, separately unique for each call and arm. This forces a new source snapshot but does not imply every lower content-addressed result is cold. Only these source bytes change during the edit samples. The original app, config, lock, source and module bytes are restored; the engine lifecycle removes only the owned temporary container, leaves the original engine untouched/stopped, and retains the volume.

Default CLI progress is retained. An empty configuration directory and whitelisted environment prevent production Cloud export. Complete-command timings use blocking waitpid timestamps; engine counters and guards are outside the interval. Two wcprof commands are excluded from ordinary timing results. The profile should test whether authored backend producer dispatch disappears from listing, and separately attribute `artifact.moduleTree` / `artifact.coreTree` work. Inclusive child intervals must not be summed as a critical path.

This does not measure fresh-volume cold startup, actual check runtime, services, SDK generation, or production Cloud. Actual execution, failed/updated service behavior and edited test bodies belong to the separate prerequisite correctness gate.
