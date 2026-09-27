# Docker Exec API as a tunnel transport

Source-only audit at Dagger `e6e723145e914680b9daea080046c55eb6ccc233`. No implementation, package listing/build, tests, Docker calls, or performance measurement was performed for this audit.

**A direct Exec API adapter is a plausible, narrower alternative to automatically exposing the engine's Unix socket.** It would remove the host `docker exec` process while retaining the daemon's ExecCreate/ExecStart authorization, the container's `buildctl dial-stdio` process, and the ordinary container/image driver. It does not remove container exec/runc startup. The measured direct-engine-socket benefit is not its predicted benefit.

## Existing path and reuse limits

`engine/client/drivers/docker.go:113` starts `docker exec -i <container> <args>` through Docker's `commandconn`. The same backend implementation serves Docker, Podman, Finch and nerdctl. `container.go:232` retains one initial tunnel plus three proactive warm tunnels after the first response byte. A causal API experiment must keep that topology, availability checks, provisioning, image loader and empty EngineID unchanged.

`engine/client/imageload/docker.go` is also subprocess based (`load`, `tag`, `save`); it does not provide a Docker API/context client to reuse. Current engine/client imports Docker CLI config and commandconn, not its full command package. A go.mod dependency is not evidence that its API client is already linked or initialized.

There is a version boundary: Dagger pins Docker CLI v29.3.1 and legacy docker/docker v28.5.2. CLI v29's context endpoint package and `command.NewAPIClientFromFlags` use the newer `moby/moby/client` and `moby/moby/api` module paths. They are absent from Dagger's current go.mod/go.sum; Docker CLI's vendor.mod pins client v0.3.0/API v1.54.0. Importing those packages would require dependency work. Added startup cost has not been measured.

## Endpoint and authority must match

The useful full-context entry is the error-returning `command.NewAPIClientFromFlags`, not `DockerCli.Client`: the latter can call os.Exit. Calling the whole `DockerCli.Initialize` also changes global log settings, filters OTel environment variables and may apply context GODEBUG settings. That is unsuitable as a casual embedded initialization step.

An equivalent resolver must retain Docker config/current-context selection, DOCKER_HOST/DOCKER_CONTEXT precedence, DOCKER_CONFIG, TLS verification/certificates, API-version override, configured HTTP headers, and SSH helpers. `flags.NewClientOptions()` alone does not set TLS defaults: InstallFlags and SetDefaultOptions perform that work. Legacy client.FromEnv does not load named contexts or config HTTP headers and is not an equivalent replacement.

For this pinned CLI, explicit context wins; explicit host and nonempty DOCKER_HOST select the default context before consulting DOCKER_CONTEXT/currentContext. Named endpoints include TLS data; SSH endpoints still start SSH/remote `docker system dial-stdio`. A full adapter can work through Desktop/rootless/remote daemons without binding the engine socket into the host, but the context matrix must prove this.

An existing runner-URL `context` value is currently inserted after the container name, into the command argument vector (`container.go:278`, `docker.go:113`). The API prototype must preserve that vector, not silently reinterpret it as a Docker-global context option. Its intended contract is a separate question.

ExecCreate and ExecAttach use the normal daemon HTTP routes; authorization middleware still handles those requests with their TLS identity and headers. This does not preserve arbitrary host `docker` wrapper-script policy, nor imply that authorization plugins will accept different client headers. Keep unsupported backends/wrappers on their established subprocess path. Decide eligibility before an exec is created: do not fall back after denied authorization, transport failure or partial ExecCreate/Attach and accidentally repeat an operation or switch authority.

## The stream adapter is the essential correctness work

* Request AttachStdin/Stdout/Stderr, TTY=false, the original argument vector, and no new user/env/privileged settings. TTY mode can alter bytes and merges stderr into the protocol.
* Non-TTY ExecAttach output has Docker stdout/stderr framing. Read the returned HijackedResponse.Reader through the demultiplexer, not an unframed raw socket. It must preserve bytes already buffered during HTTP upgrade. Writes go to the hijacked connection; keep stderr bounded and separate from Dagger's protocol.
* Preserve half-close where supported. `cmd/dialstdio/main.go` closes the engine write side on stdin EOF and waits for stdout; it returns immediately when stdout ends. A slow reader, late final telemetry and cancellation must not leave a demultiplexer goroutine blocked on its output pipe.
* Current commandconn deliberately detaches the command from the dial request context, and Close closes pipes then joins the host process (SIGTERM, then a bounded SIGKILL fallback). A successfully returned API tunnel must likewise outlive a short dial/request context. Close must unblock and join its owned pumps. Concurrent/repeated close and partial initialization need deterministic ownership.
* The daemon starts attached exec with a background context. Closing the HTTP connection is not a general process-kill API. For this stdio proxy, prove EOF terminates the remote process without leaking it; do not claim that closing a hijacked socket synchronously joins an arbitrary container process. Docker CLI normally inspects exit status after streaming completes, so preserve meaningful missing-command/nonzero-exit errors rather than returning only EOF.
* A connector currently has no Close method and backend instances are global registrations. Do not put a credential-bearing API client in that global backend. A minimal proof can own one short-lived API client per tunnel; its Close closes idle HTTP connections, while the hijacked connection remains separately owned until adapter Close. Sharing a per-connector negotiated client is a later ownership change requiring a close contract, not a free global cache.
* Docker's legacy client enables OTel HTTP instrumentation by default. An embedded client can introduce new spans containing API paths/container IDs. Choose an explicit tracing policy and fixed-label diagnostics for the proof; do not accidentally change telemetry volume/privacy while measuring subprocess removal.

## Smallest useful next experiment

First implement an isolated, explicit opt-in adapter for the real Docker backend and a clearly declared supported endpoint configuration, keeping the subprocess default. A deliberately restricted local Unix-daemon proof can use the already pinned legacy client, provided configuration validation rejects named/ambiguous contexts and headers it cannot reproduce. This establishes the mechanism without claiming full context support. A production design should use a shared, tested Docker context resolver instead of perpetuating a second incomplete configuration interpretation.

Before a CLI build, fake-daemon tests should cover framed/buffered stdout plus stderr, bidirectional bytes, early Attach/Create errors with no retry, API-version negotiation, exact exec options, delayed readers, body lifetime after dial-context cancellation, CloseWrite, concurrent Close and joined pumps. Add a real Docker correctness gate for actual `buildctl` byte transport/exit, inherited container settings and remote exec termination, then reuse the connector's warm-tunnel tests. Context/TLS/SSH/Windows and compatible-backend fallback remain separate production gates.

Measure two matched CLIs or one opt-in binary against the same owned engine/container and same image loader. Keep initial plus three proactive tunnel requests identical, use exact-flow primers and fresh input edits, and include complete CLI cleanup in wall/CPU measurements. Count API create/start requests and host subprocesses using fixed numeric diagnostics. Measure binary startup/import cost separately. Start with core/workspace/call/generate; extend only if the causal result warrants it.

Compared with automatic engine Unix sockets, this avoids new image mounts, host socket permissions/discovery, and a capability that bypasses per-exec daemon authorization. It retains a container process per tunnel, and adds context/HTTP stream adapter responsibilities. It is worth a bounded proof, not yet a production recommendation or a claimed millisecond saving.
