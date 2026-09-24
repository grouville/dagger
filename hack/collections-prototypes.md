# Rebuild the measured prototypes

These experiments preserve Dagger's content-addressed result caching. They
are not release-ready changes. The [normal-mode report](collections-normal-mode-performance.md)
measured 3.053 s with both, compared with 4.852 s for the committed engine/CLI.

The build helper applies the archived Dang patch to a fresh copy of the
checksum-verified v2.1.4 module, uses a Go build overlay for the two engine
parser calls, and writes a patched copy of the measured TypeScript SDK. It
does not modify the repository's go.mod, the Go module cache, or the input SDK.
No machine-specific dependency replacement is committed to production code.

```sh
python3 hack/build-collections-prototypes.py \
  --output /tmp/collections-prototype-build \
  --sdk-dir /path/to/greetings-api/.dagger/modules/frontend/sdk
```

The input SDK must be the unchanged bundle from greetings-api `14d684f`; its
hash is checked before building. The output contains `engine`, `dagger`,
`sdk/`, and a manifest with dependency and binary hashes. Use the engine binary
in a separately named development engine image with the same builtin SDKs,
and copy `sdk/` into a disposable greetings-api checkout's frontend directory.
The script does not deploy containers or modify the application for you.

## What must improve before upstreaming

**Dang:** inference mutates syntax nodes. Every consumer must own a separate
tree. Replace the prototype's reflective clone with a maintained typed clone
or immutable syntax plus separate evaluation state. Establish a retained-byte
budget, rather than only entry/source-size caps. Preserve diagnostic filenames,
parse-error behavior, concurrent miss coalescing and content-based invalidation.
Run the complete Dang and affected Dagger CI after the focused ownership/race
tests. Publish a Dang library change before updating the engine dependency;
the build overlay is only an experiment delivery mechanism.

**TypeScript:** move the small lazy-import helper into the actual SDK build
pipeline, or remove the unnecessary loader transformation upstream in tsx.
The current rewrite deliberately accepts one known bundle hash. It must not
be turned into a generic regex-based JavaScript transform. Verify regenerated
modules and standalone clients, Node/Bun/Deno, HTTP and HTTPS telemetry, source
maps, and error stacks. Regeneration must produce the optimized files itself;
hand-edited generated output will otherwise be replaced or flagged stale.

Neither experiment caches discovery answers. The syntax cache is process-local
and keyed by source content; the SDK helper preserves lazy builtin imports.
Warm improvements do not establish a cold-start improvement. Sources, patches,
focused validation and measurements remain in the linked reports.
