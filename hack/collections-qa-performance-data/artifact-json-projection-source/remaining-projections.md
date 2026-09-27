The measured prototype changes only the two JSON item readers. Three analogous
call sites remain unchanged: `artifactDimensions` in internal/cmd/dagger/artifacts.go
selects an ID then projects dimensionDefinitions; `readArtifactTypes` selects an
ID then projects __typeDefinitions; `artifactLoadFailures` in artifact_execution.go
first narrows to dag://*/load, then selects an ID and projects items { uri loadError }.
Each can add one avoidable ID materialization request when its selection has not
cached an ID. Whether a command reaches one or several readers depends on its path.
A Ref selection does not imply that its ID field is memoized; changing Ref.ID globally
would change validation semantics and is outside this experiment.

The existing artifactWorkspaceReuse fake server was adapted only to wrap the JSON
leaf along the actual composed response path. Its Go/TypeScript/Dang global aliases,
filtered module, nested collections and original row assertions remain unchanged.
GraphQL errors and cancellation remain errors, but a composed request can naturally
change the raw GraphQL error path to include its selection ancestors.
