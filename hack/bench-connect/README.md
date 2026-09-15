# Connect benchmark and verification matrix

`bench.sh` measures `dagger query '{version}'` (connect plus one trivial round trip) over
each transport the CLI can use to reach a local docker engine, on the same engine container,
interleaved samples, medians. It answers one question: what does a command pay before it
does any work.

## Why the local endpoint exists

Every connection to a docker-run engine used to go through `docker exec buildctl
dial-stdio`. The daemon runs a `runc exec` for each one (~40ms), the CLI opens four per
command, and before that it listed every container on the host. None of that is the
engine's work. With the local endpoint the CLI creates the engine container with a
loopback port protected by a token it generated, records both in a private directory, and
later commands connect directly.

## Results (Linux, docker 28, ripgrep-sized workspace, medians)

| What | Before | After |
|---|---:|---:|
| `dagger query '{version}'` | 300ms (exec tunnel) | 150-170ms (endpoint) |
| cached `dagger check rust:check`, engine with the other perf branches | 368ms | 153ms (native cargo: 105) |
| connect span in the client timeline | 220ms | below 8ms |
| exact hit, same engine, exec tunnel vs endpoint | 479ms | 342ms |

`bench.sh -n 8` on this host (Linux, docker 28, same engine container, medians / min), plus
the CLI from main against the same container for the true "before" (it spawns the docker CLI
and lists all containers, 127 on this host):

```
transport    median      min
endpoint       96.5       85     token-protected loopback port (this series)
exec          209.5      187     exec tunnel over the daemon API (commit 1, and the fallback)
container     191.5      178     container:// (exec tunnel, no discovery)
main CLI        529      493     docker CLI spawns + docker ps -a + exec tunnel (today)
```

The reproduction is `dagger query '{version}'`: connect plus one trivial round trip, nothing
else. `bench.sh` runs it interleaved over the transports; the main-CLI line is the same query
with a CLI built from main (`DAGGER_ENGINE="image://<image>?container=<name>&volume=<name>"`).

The first samples after an engine start are slower (dagql cache load); take them after a
warm-up command, as the script does.

The Go benchmark isolates one usable connection (dial plus the engine's first reply, since an
exec tunnel is only live once the daemon has started the process), on the same container:

```
DRIVER_TEST=1 DAGGER_BENCH_ENGINE_IMAGE=<engine image> \
  go test ./engine/client/drivers -run xxx -bench ContainerConnect -benchtime 20x

BenchmarkContainerConnect/endpoint-8   20     294362 ns/op
BenchmarkContainerConnect/exec-8       20   24526528 ns/op
```

A command opens four connections, which is where the ~100ms per command comes from.

## Verification matrix

| Use case | Path taken | Verified |
|---|---|---|
| Local docker, Linux, first run | CLI creates the container with `-p 127.0.0.1:<port>:<port>`, the endpoint directory bind-mounted read-only, `--token-addr tcp://0.0.0.0:<port> --token-file /run/dagger/endpoint/token` | yes: `docker inspect` shows the loopback-only binding and args; files 0600 in `$XDG_STATE_HOME/dagger/engines/<container>` (`TestImageDriverLocalEndpoint`, `TestImageDriverCreatePublishesLocalEndpoint`) |
| Local docker, later commands | endpoint probed first, discovery skipped, all dials over the port after the handshake | yes: no connect span above 8ms; `docker ps`/`docker version` never run |
| Wrong token, or a client that does not answer the challenge | engine closes the connection before any protocol byte; the client never sent the token | yes: `nc` gets the challenge line and nothing else (`TestTokenListener`) |
| Something else listening on the recorded port (engine down, rogue process) | the client aborts when the peer cannot prove it holds the token; the token was never sent | yes: `TestEndpointHandshakeRejectsImpostor`; a silent peer costs one 3s probe, then the exec tunnel |
| Token file corrupted or removed, port not answering | exec tunnel through the daemon API, as before; the endpoint is not retried within the same process | yes: 0.23s (`TestImageDriverLocalEndpoint`, `TestContainerConnectorPrefersLocalEndpoint`) |
| State directory lost while the container exists (reboot with a runtime dir would have been the same) | docker recreates the bind source as an empty directory; the engine starts without the token listener and says so; the CLI uses the exec tunnel for that engine | yes: `docker stop`, `rm -rf` the directory, next command 2.6s and the engine is running (`TestImageDriverLocalEndpoint`) |
| Two CLIs create the same engine at once | the loser drops the endpoint record it overwrote; both use the exec tunnel until the next engine upgrade | by construction (`create`, the `errContainerAlreadyExists` branch) |
| Engine created by an older CLI (no files) | exec tunnel | yes by construction: `loadLocalEndpoint` fails, `create` finds the container by name |
| Engine upgrade (new image) | new container name → new port and token; old engines and their endpoint records cleaned up on create | by construction (`create` path unchanged apart from the endpoint; `garbageCollectEngines` removes the state dir) |
| User-published port `?port=N` | `--addr tcp://0.0.0.0:N` stays unauthenticated; only `--token-addr` requires the token | by construction after the `--token-addr` split; `TestImageDriverCreatePublishesLocalEndpoint` pins the args |
| Remote docker daemon (`DOCKER_HOST=ssh://`, `tcp://`) | no endpoint (the port would be on the other host, a bearer token must not cross a network); exec tunnel | yes: `DOCKER_HOST=ssh://localhost` creates the container without token flags, no endpoint dir, commands work (1.8s each = ssh per connection, unchanged) |
| `container://name` (user-managed engine) | exec tunnel, no discovery | yes: measured, unchanged |
| `unix://`, `tcp://`, `tls://`, `ssh://`, `kube-pod://` engines | dial drivers, untouched | by construction: `dialDriver` does not go through `imageDriver` |
| Dagger Cloud engines | cloud driver, own credentials, untouched | by construction: `daggerCloudDriver` does not go through `imageDriver` |
| Nested clients (module code) | session port inside the engine, untouched | yes: module checks ran through the endpoint-connected CLI |
| macOS (Docker Desktop, Colima, OrbStack) | same as Linux: loopback port forwarded by the runtime; endpoint directory under `~/Library/Application Support/dagger/engines` with the same 0700/0600 checks | not run here, needs a Mac; port publishing and bind mounts from the home directory are standard there |
| Windows, Linux CLI inside WSL2 | the Linux path | not run here, needs a machine |
| Windows, native CLI | exec tunnel; no endpoint is created because the ownership check that keeps the token private needs mode bits, not ACLs (`endpoint_windows.go`) | by construction; cross-compiles |
| Multiple users on one daemon | the creating user has the endpoint; others have no token file and use the exec tunnel | by construction |

## Trust model

The token is 32 random bytes in a 0600 file under a directory the CLI verifies it owns
(mode 0700, no symlink), in the user's state home so it survives reboots with the
container. The port is bound to 127.0.0.1. Before any protocol byte the two sides run a
mutual challenge-response: the engine sends a nonce, the client answers with an HMAC-SHA256
of both nonces under the token plus its own nonce, and the engine answers with its own HMAC.
The token itself never crosses the connection, so a process that binds the port while the
engine is down learns nothing it can replay and cannot pass for the engine; the client
aborts before sending anything else. The engine gives a client 10s to answer and closes on
a bad or missing proof; the client gives a peer 3s. Another local user needs the file and
cannot read it; loopback traffic is not readable without root. This is the boundary
docker-group membership already gives. Rotation is the container's lifetime.

Compared with the alternatives: a bearer token sent as a preamble (the first version of
this change) would leak to anything listening on the port while the engine is down; mTLS
gives the same mutual proof with certificates, a CA and rotation to manage, which a
loopback endpoint does not need.
