# Can the attachables helper itself become smaller?

Yes: it has a clean package boundary worth testing, although the largest
remaining initialization work is not all removable through that boundary.
This is source analysis and reduction of an existing diagnostic capture only;
no new build, test, engine query or runtime measurement was performed.

`mainSession` needs four things from `engine/client`: `SessionAttachable`,
`ConnectSessionAttachables`, `SocketProvider` and `NewFilesyncer`. Importing that
package also links its other source files and dependencies: provisioning
drivers, image loaders, Buildkit client, registry auth, the public Go SDK client,
analytics, Cloud client, and telemetry labels. Those are not used to serve the
already-connected nested attachables channel.

Concrete source paths:

- `engine/client/client.go` imports `drivers`, `imageload`, `analytics`,
  `engine/telemetry`, `dagger.io/dagger`, Buildkit client/authprovider. Its
  attachables server/upgrade implementation is a self-contained block around
  lines 746–850: HTTP upgrade, method advertisements, trace propagation, gRPC
  health registration, connection serving and joined lifetime.
- `engine/client/imageload/containerd.go` imports the full containerd client and
  registers that image-loader backend at init time; no nested helper request
  provisions an engine or imports an image store through it.
- `engine/client/filesync.go` and `socket.go` contain the actual nested providers.
  Moving only the server block would not help: either remaining import of
  `engine/client` retains the whole package graph.
- `engine/telemetry/labels.go` imports go-git and GitHub metadata support. The
  helper preserves trace propagation, but does not call label enrichment.

Smallest coherent experiment: move the attachables transport/server plus the
filesync and socket provider implementations into a dependency-light
`engine/session/attachables` package, then have `cmd/init` import it directly.
Keep forwarding constructors/type aliases in `engine/client` so existing API
callers retain the same methods and structs. Move the relevant private-helper
tests with their implementation rather than exporting internals solely for
tests. Do not copy an independent implementation into cmd/init or add another
cache. This separates engine provisioning from serving an existing connection.
Both the old client and the helper should use the same transport/provider code.

The new package still needs `engine` for metadata and filesync protocol types;
that package currently imports control protobufs and Cloud auth. It still needs
gRPC, HTTP/2, telemetry propagation, fsutil, filesync and SSH protocol bindings.
Some dependencies reached through provisioning may also remain reachable
through these legitimate paths. A subsequent exact `go list -deps` difference
and matched build are needed before claiming which packages disappear.

The most expensive observed records warn against overpromising:

| Package initialization record | Diagnostic clock | Allocation bytes |
| --- | ---: | ---: |
| AWS SSO endpoint table | 1.30 ms | 77,184 |
| distribution/reference regex tables | 1.00 ms | 414,552 |
| AWS SSM endpoint table | 0.78 ms | 82,768 |
| Vault API | 0.64 ms | 315,672 |
| go-cmp | 0.47 ms | 178,568 |
| protobuf protodesc | 0.43 ms | 177,328 |

These come from one separately instrumented capture, not ordinary startup
timings or exclusive call-stack attribution. The complete capture has 505 init
records and approximately 3.40 MB reported package-init allocations. Numeric
package-prefix aggregates are in `numeric.json`; their grouping does not prove
that a dependency can be removed.

In particular, `cmd/init` directly imports `secretprovider`. Its resolver map
retains AWS, GCP, Vault and 1Password support even when no secret is requested.
AWS endpoint tables and Vault initialization therefore survive the client
extraction. Removing those providers, routing their reads to an ancestor
session, or changing TTL/credential behavior is not a package-only optimization:
the nested environment, files, credential state and command authority matter.
A lazily started separate secret helper could be explored later, but adds a
protocol/lifetime change and shifts startup cost to first use. It is outside
this minimal candidate.

Likewise, terminal UI dependencies are not solely an accidental client import.
`engine/session/git/git_push_ssh.go` imports `huh` and the prompt interface to
build a passphrase form; the interface itself mentions `*huh.Form`. The nested
helper passes no prompt handler, but Go still initializes the imported graph.
A typed prompt abstraction independent of a concrete UI could separate this
later, while keeping the exact passphrase/lifetime policy. It is a distinct
small architectural candidate, not a justification for deleting Git support.

The client extraction should preserve session metadata/header authority, all
advertised methods, gRPC health behavior, upgrade/ACK ordering, propagation,
FD3 readiness, provider child ownership, cancellation and connection cleanup.
Existing lifetime, filesync, parent-directory metadata, search, socket and
proxy tests should move or run unchanged against aliases. Validate exported
types/call sites and real Go/Python/TypeScript nested reads before timing.

The measured heavy-versus-light PID1 startup reduction was only about 8.7 ms per
paired host process, so a second extraction can remove only part of the remaining
helper startup in that setting. It is worth a bounded compile/dependency/startup
proof because the abstraction is useful and generic, but not a promise of a
large whole-command improvement. It does not duplicate SDK entrypoint/codegen
work: it changes the engine's attachables helper shared by SDK languages.

Ranked follow-ups:

1. **Attachables package extraction:** smallest behavior-preserving candidate.
   Prove the dependency difference and ordinary process startup first, then
   decide whether the reduction warrants moving the provider/test code.
   AWS/Vault/GCP and Git prompt dependencies remain; no removed-count estimate
   is established yet. Full CLI users still import their provisioning client,
   so this primarily helps attachables-only consumers such as nested helpers.
2. **Inject a narrow secret-prompt callback from interactive callers:** Git can
   request a passphrase through a UI-independent function taking context and
   display text; the interactive caller constructs the existing password form.
   Nil keeps the existing noninteractive encrypted-key behavior. This must move
   the `huh.Form` type dependency out of the Git package, not merely add another
   runtime branch. Preserve cancellation, prompt policy and the rule that the
   passphrase never enters engine RPCs. The seven terminal-UI-prefixed records
   account for only 0.284 ms in this diagnostic, so this is low priority on
   performance grounds alone.
3. **Start specialized secret-provider code only on demand:** a separate,
   per-execution owned helper could keep AWS/Vault/GCP/1Password imports out of
   the common attachables process. Keep env/file/cmd schemes local. Launch the
   specialized helper on first request with the same captured environment,
   filesystem/credential authority and cancellation, and retain its lifetime
   so provider caches/TTL/concurrency remain equivalent. This shifts cost to
   first secret use and adds private IPC, error and cleanup semantics. It is a
   larger design, not a safe provider deletion or an optimization to enable now.

For context, AWS-prefixed records sum to 2.890 ms and Vault to 0.640 ms in the
existing instrumented capture. Prefix groups are not exclusive call graphs or
removable wall-time estimates, and shared Google RPC/protobuf dependencies remain
necessary even if a specific cloud provider moves. There is no predicted
cumulative CLI improvement from adding these numbers.
