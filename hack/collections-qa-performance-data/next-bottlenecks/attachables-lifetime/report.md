# Preserve host attachables through cancelled-command shutdown

The service benchmark exposed a lifecycle error rather than an expensive
operation that needs a new cache. A normal `container.from("busybox:1.37")`
lookup should record its OCI digest in the workspace lock. Repeated `dagger
up web`, stopped with SIGINT after serving the correct HTTP body, did not
persist that lock. Each later invocation paid for tag resolution again.

The isolated native-module diagnostics distinguish lookup and cancellation:

| Fresh Git fixture command | Ordinary OCI lock persisted |
| --- | --- |
| Finite native `api call image` | Yes |
| Finite native `api call web hostname` | Yes |
| `up web`, SIGINT after exact HTTP readiness | No |
| `up web`, SIGINT one second after readiness | No |
| Finite core `container from ... image-ref` | Yes |

The first four-case trial is `service-lock-write-v1`; its frozen driver hash
matches provenance and exactly four results. The finite-web supplemental
trial is separately recorded in `service-lock-web-finite-v1` and is not
relabeled as part of the four-case trial.

## Source cause and isolated change

`Client.startSession` and `startE2ESession` started the long-lived gRPC host
attachables server with the connecting command's context. Their
`withClientCloseCancel` wrapper also preserves cancellation of that parent.
`SessionAttachablesServer.Run` stops the server and closes the connection when
that context is cancelled. Thus SIGINT can remove filesync/host access before
`Client.Close` asks the engine to flush workspace lock updates. The engine's
`WithoutCancel` around lock flushing cannot restore a disconnected client
transport.

`lifetime.patch` shares a small `runSessionAttachables` helper between the two
paths. It serves using the existing detached `Client.internalCtx`, additionally
bounded by closeRequests. The helper cancels its wrapper on return, avoiding
an idle watcher after transport exit. Command/API request cancellation stays
unchanged. Host services remain available for the already-existing bounded
shutdown protocol, and stop when Close proceeds or client initialization
fails. No engine patch, image reference, locking policy or result-cache
policy changes.

The engine does already flush workspace locks before closing host attachables.
This fix makes the client's transport lifetime respect that ordering.

## Verification completed

`session_attachables_lifetime_test.go` calls the actual ordinary and E2E
session setup methods. A fake engine performs their real HTTP upgrade and
uses real gRPC health requests over a net.Pipe. After command cancellation,
the fake `/shutdown` handler verifies host RPCs still work; after `Close`,
the test verifies that transport is closed. A second case verifies internal
client-lifetime cancellation finishes the transport and its errgroup.

The unchanged baseline fails the cancellation regression in both paths.
The candidate passes both paths and the internal-lifetime shutdown check,
including the Go race detector. This is not a test-only implementation of
the session loop. Test logs and source overlays are beside this report.

The isolated CLI is `dagger-attachables`, SHA256
`c5b8dd92adf66f061cceed037cbb4bd32844dfb5071e0fb17020b0fc29f88fce`, built
against committed HEAD `4b488e191f0a6659525768f917091f67d2077c28` with only
`engine/client/client.go` replaced by this candidate. Its Go tests are
included in the overlay but do not enter the CLI build. After the actual
service validation, the exact tested source and test file were applied to
the shared tree. `applied-source.json` records their matching hashes. No
commit has been made by this agent.

## Real service A/B completed

The production baseline CLI includes the committed sparse-export fix. The
candidate adds only this attachables lifetime change. Both use the same
retained engine, warm BusyBox image, local-only telemetry environment and
ordinary tag expression, starting in separate fresh Git workspaces with no
lock. There are fourteen unprofiled commands: first service start, three warm
reruns and three real input edits for each CLI. Two separate profiled commands
follow. The frozen driver/provenance hashes match all sixteen results, and
the original source workspace is unchanged. Raw evidence is in
`cli-key-scaling/service-lifetime-ab-v1`.

| Boundary | Baseline median | Lifetime fix median |
| --- | ---: | ---: |
| Warm exact HTTP readiness (n=3) | 1.264645 s | 0.476418 s |
| Real edit to exact HTTP readiness (n=3) | 1.353767 s | 0.443640 s |
| Warm full cancelled CLI, including cleanup (n=3) | 1.392663 s | 0.592902 s |
| Real edit full cancelled CLI, including cleanup (n=3) | 1.456080 s | 0.588881 s |

Every candidate invocation persisted the ordinary OCI lock; every baseline
invocation lacked it after cancellation. All six candidate warm/edit HTTP
readiness samples were below 500 ms (404–494 ms). This is service readiness,
not full foreground CLI exit. All exact response-body and tunnel cleanup
checks passed. The three edit markers have equal lengths and unique bytes
per CLI (`edited-{i}-{variant initial}`); the timed order alternates within
warm and edit phases. Content caching below these changed inputs remains
ordinary Dagger behavior.

The first empty-lock readiness samples were 1.352713 s baseline and 1.485244 s
candidate. There is no first-run improvement claim. This is not a fresh-engine
or fresh-image cold benchmark.

Separate wcprof captures show the executed Container.from call falling from
682.363 ms to 1.126 ms, and its enclosing Dang invocation from 735.344 ms to
26.948 ms. Those intervals overlap and must not be added. Both captures have
zero dropped events. The causal improvement is preserving the existing
automatic lock update during shutdown, so later commands use Dagger's normal
immutable image identity. There is no new cache or manual digest pin.

## Separate error-reporting defect

`Client.shutdownServer` currently ignores HTTP status and returns only the
response body Close error. The engine can return an error for failed lock
export while the CLI appears successful. `shutdown-status.patch` and
`shutdown_status_test.go` are a separate change, with bounded error-body
reading. The baseline regression fails because 401 and 500 both return nil;
the isolated status candidate passes 200/204/401/500 cases and verifies body
closure. These sources are not applied to the shared tree and are not in the
measured lifetime CLI. Keep their correctness attribution separate from the
service performance comparison.
