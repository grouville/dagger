# DefaultPath + Ignore Empty Directory Investigation

## Background
- v0.19.0 showed contextual defaults (`+defaultPath="."` + `+ignore`) as
  `Host.directory(path: "/tmp/...", exclude: ["*", "!src"])`.
- v0.19.1 (after PR #11034 "User defaults: persist any dagger function argument to .env") now prints the dependency module path (`modules/my-module`) whenever the contextual directory reduces to an empty scratch directory. The engine behaviour is unchanged; only the CLI call tree regressed.

## Observed Symptom
- `dagger call source entries` (v0.19.1) renders:

  ```
  src: Host.directory(path: "/…/modules/my-module", include: [".env"]): Directory!
  ```

  even though `src` actually comes from `+defaultPath="."` with `+ignore` removing everything but `src/`.

- If a real `.env` is added at that dependency path, the CLI starts showing the host path again because the renderer now uses the real `Host.directory` call. That confirmed the issue is purely a rendering artefact.

## Key Checks & Evidence

### Engine Behaviour (unchanged)
- `core/modfunc.go:setCallInputs` emits `📨 … converted=…` — the base64 payload decodes to `Host.directory(path: "/tmp/dagger-issue-defaultPath", exclude: ["*", "!src"], noCache: true)`.
- `core/modulesource.go:LoadContextDir` emits `🛣️ LoadContextDir: … returned-digest=sha256:0e5db883…` for that scratch directory.
- `core/directory.go:Entries` emits `📂 Directory.Entries: digest=sha256:0e5db8…`, proving the listing uses the same digest and returns `[]`.

### Renderer Regression
- `dagql/idtui/frontend.go:renderCall` logged `🎨 renderCall: parent=source … friendly=false collapsed=true` for the contextual call and `friendly=true` for the dependency probe, so the contextual line was collapsed and the CLI printed `modules/my-module`.
- When a `.env` exists under the dependency, the probe no longer matches the scratch digest and the contextual call remains, so the CLI prints the correct path—confirming the regression is purely in the renderer.

## Next Steps
- Update the CLI renderer (`dagql/idtui/frontend.go:renderCall`) to select the most user-facing `Host.directory` call **before** simplification. Concretely:
  1. Gather all creators for the argument digest (`db.CreatorSpans[digest]`).
  2. Prefer contextual invocations (`exclude=["*", "!src"]`, `noCache=true`, matching module object) over dependency probes (e.g., `include=[".env"]`).
  3. Render that preferred call and treat it as “friendly” so the simplifier keeps it.
- Rebuild the CLI binary (`go build -o bin/dagger ./cmd/dagger`) and rerun `dagger call --rebuild source entries` to confirm the call tree now shows `Host.directory(path: "…/dagger-issue-defaultPath", exclude: ["*", "!src"], noCache: true)` even when the directory is empty.

## Useful Functions / Logs for Verification
- `core/modfunc.go:setCallInputs` (`📨`) → confirm the literal payload/digest passed into GraphQL.
- `core/modulesource.go:LoadContextDir` (`🛣️`) → observe the contextual directory digest (`sha256:0e5db8…`).
- `core/directory.go:Entries` (`📂`) → confirm the directory being enumerated matches that digest.
- `dagql/idtui/frontend.go:renderCall` (`🎨`) + helper `shouldExposeCall` → see which call the CLI renders/collapses for each argument.
