package replay

import (
	"encoding/json"
	"fmt"
	"path"

	"dagger.io/dagger"
	"github.com/dagger/dagger/hack/rust-cache/model"
	"github.com/dagger/dagger/hack/rust-cache/worker"
)

func buildBatch(client *dagger.Client, plan *model.Plan, source Source, opts BuildOptions) (*Graph, error) {
	if opts.BatchWorkers < 1 {
		return nil, fmt.Errorf("batch compiler concurrency must be positive")
	}
	actions, err := ordered(plan.Actions)
	if err != nil {
		return nil, err
	}
	var missing []model.Action
	var targets []*dagger.Directory
	seeds := append([]*dagger.Directory(nil), opts.automatic.batchSeeds...)
	for _, action := range actions {
		if retained := opts.automatic.hits[action.ID]; retained != nil {
			if opts.automatic.artifacts == nil {
				targets = append(targets, retained.target)
			}
		} else {
			missing = append(missing, action)
			if seed := opts.automatic.seeds[action.ID]; seed != nil && !opts.automatic.batchSeeded[action.ID] {
				seeds = append(seeds, client.Directory().WithDirectory(worker.Token(action.ID), seed))
			}
		}
	}
	if len(missing) == 0 {
		opts.BatchCompiler = nil
		return BuildWithOptions(client, plan, source, opts)
	}
	request := worker.Request{Actions: missing, Dependencies: plan.Actions, Packages: plan.Packages,
		Concurrency: opts.BatchWorkers, Pipelining: !opts.BatchNoPipelining}
	contents, err := json.Marshal(request)
	if err != nil {
		return nil, err
	}
	workspace := opts.SourceDirectory
	if workspace == nil {
		workspace = source.Directory(client)
	}
	target, incremental := client.Directory(), client.Directory()
	if opts.automatic.artifacts != nil {
		target = opts.automatic.artifacts
	} else if len(targets) > 0 {
		target = mergeArtifactDirectories(targets)
	}
	if len(seeds) > 0 {
		incremental = mergeArtifactDirectories(seeds)
	}
	container := client.Container(dagger.ContainerOpts{Platform: "linux/amd64"}).From(plan.Image).
		WithMountedDirectory(model.SourceRoot, workspace).
		WithMountedDirectory(model.TargetRoot, target).
		WithMountedDirectory(worker.IncrementalRoot, incremental).
		WithMountedFile(worker.Root+"/runner", opts.BatchCompiler).
		WithNewFile(worker.Root+"/request.json", string(contents), dagger.ContainerWithNewFileOpts{Permissions: 0600}).
		WithExec([]string{worker.Root + "/runner", "worker", worker.Root + "/request.json"}, noNesting())
	graph := &Graph{results: map[string]*dagger.Directory{}, BatchTrace: container.File(worker.Root + "/timings.json")}
	var allOutputs []string
	for _, action := range actions {
		retained := opts.automatic.hits[action.ID]
		operation := Operation{Action: action, Files: map[string]*dagger.File{}}
		if retained != nil {
			graph.HistoryHits++
			operation.Stamp = retained.stamp
		} else {
			operation.Container = container
			operation.Stamp = container.File(path.Join(worker.Root, "actions", worker.Token(action.ID), "execution"))
		}
		for _, output := range action.Outputs {
			if operation.Container == nil {
				operation.Files[output] = retained.target.File(targetRelative(output))
			} else {
				operation.Files[output] = container.File(output)
			}
			allOutputs = append(allOutputs, targetRelative(output))
		}
		graph.Operations = append(graph.Operations, operation)
	}
	graph.Artifacts = client.Directory().WithDirectory(".", container.Directory(model.TargetRoot),
		dagger.DirectoryWithDirectoryOpts{Include: allOutputs})
	// Retain the batch's three output trees once. Manifest entries point to
	// individual crates inside them, avoiding N copies and N-level joins of
	// incremental state. The per-crate logical keys remain independent.
	graph.batchSnapshot = client.Directory().WithDirectory("target", graph.Artifacts).
		WithDirectory("incremental", container.Directory(worker.IncrementalRoot)).
		WithDirectory("actions", container.Directory(worker.Root+"/actions"))
	return graph, nil
}
