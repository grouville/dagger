// Package replay turns recorded compiler invocations into native Dagger operations.
package replay

import (
	"context"
	"fmt"
	"path"
	"slices"
	"strings"
	"sync"
	"time"

	"dagger.io/dagger"
	"github.com/dagger/dagger/hack/rust-cache/model"
	"golang.org/x/sync/errgroup"
)

// Keep diagnostics in a small directory. Engines without the contenthash file
// fast path walk a file's parent; a marker at / scans the entire toolchain image.
const stampPath = "/rcexp-meta/execution"

type Operation struct {
	Action    model.Action
	Container *dagger.Container
	Files     map[string]*dagger.File
	Stamp     *dagger.File
}

type Graph struct {
	Operations  []Operation
	Artifacts   *dagger.Directory
	Incremental *dagger.Directory
}

// BuildOptions exposes an explicit, single-crate incremental experiment. The
// seed remains an ordinary cache-key input; this does not implement cache hints.
type BuildOptions struct {
	IncrementalCrate string
	IncrementalSeed  *dagger.Directory
}

type ActionReport struct {
	ID            string            `json:"id"`
	Crate         string            `json:"crate"`
	Execution     string            `json:"execution"`
	Digests       map[string]string `json:"digests"`
	DemandSeconds float64           `json:"demand_seconds"`
	DigestSeconds float64           `json:"digest_seconds"`
}

type Report struct {
	ReplaySeconds float64        `json:"replay_seconds"`
	Actions       []ActionReport `json:"actions"`
	Driver        *DriverTimings `json:"driver,omitempty"`
}

// DriverTimings separates CLI setup and output transfer from graph evaluation.
// ReadySeconds ends when artifact export completes; process shutdown is measured
// externally when benchmarking the full user command.
type DriverTimings struct {
	SourceSeconds      float64 `json:"source_seconds"`
	ConnectSeconds     float64 `json:"connect_seconds"`
	GraphSeconds       float64 `json:"graph_seconds"`
	ExportSeconds      float64 `json:"export_seconds"`
	IncrementalSeconds float64 `json:"incremental_seconds,omitempty"`
	ReadySeconds       float64 `json:"ready_seconds"`
}

// Build creates only recipes. The caller chooses when and on which engine to demand them.
func Build(client *dagger.Client, plan *model.Plan, source Source) (*Graph, error) {
	return BuildWithOptions(client, plan, source, BuildOptions{})
}

func BuildWithOptions(client *dagger.Client, plan *model.Plan, source Source, opts BuildOptions) (*Graph, error) {
	if err := Validate(plan, source); err != nil {
		return nil, err
	}
	if opts.IncrementalSeed != nil && opts.IncrementalCrate == "" {
		return nil, fmt.Errorf("incremental seed requires a crate")
	}
	if opts.IncrementalCrate != "" {
		if _, err := SeedCompatibility(plan, opts.IncrementalCrate); err != nil {
			return nil, err
		}
	}
	actions, err := ordered(plan.Actions)
	if err != nil {
		return nil, err
	}
	base := client.Container(dagger.ContainerOpts{Platform: "linux/amd64"}).From(plan.Image)
	graph := &Graph{Artifacts: client.Directory()}
	byID := map[string]Operation{}
	artifacts := map[string][]*dagger.File{}
	packageSources := source.packageSources(plan.Packages)
	packageDirs := map[string]*dagger.Directory{}
	for _, a := range actions {
		if packageDirs[a.PackageRoot] == nil {
			packageDirs[a.PackageRoot] = packageSources[a.PackageRoot].Directory(client)
		}
		ctr := base.WithMountedDirectory(a.PackageRoot, packageDirs[a.PackageRoot]).WithWorkdir(a.Cwd)
		// rustc discovers indirect dependencies through -L as well as --extern.
		closure := map[string]bool{}
		var collect func(string)
		collect = func(id string) {
			if closure[id] {
				return
			}
			closure[id] = true
			for _, dep := range byID[id].Action.Dependencies {
				collect(dep)
			}
		}
		for _, dep := range a.Dependencies {
			collect(dep)
		}
		bundles := map[string][]*dagger.File{}
		for _, id := range sortedKeys(closure) {
			op := byID[id]
			for _, filename := range sortedKeys(op.Files) {
				// dep-info is bookkeeping, not a compiler dependency.
				if path.Ext(filename) == ".d" {
					continue
				}
				bundles[path.Dir(filename)] = append(bundles[path.Dir(filename)], op.Files[filename])
			}
		}
		for _, dir := range sortedKeys(bundles) {
			ctr = ctr.WithMountedDirectory(dir, client.Directory().WithFiles(".", bundles[dir]))
		}
		// The nonce is an output, never an argument or a dependency input.
		cmd := []string{"sh", "-ec", "mkdir -p \"$1\" " + path.Dir(stampPath) + "; shift; cat /proc/sys/kernel/random/uuid > " + stampPath + "; exec \"$@\"", "rcexp", model.Option(a.Args, "--out-dir"), a.Compiler}
		cmd = append(cmd, a.Args...)
		if a.Crate == opts.IncrementalCrate {
			seed := opts.IncrementalSeed
			if seed == nil {
				seed = client.Directory()
			}
			ctr = ctr.WithMountedDirectory(incrementalPath, seed)
			cmd = append(cmd, "-C", "incremental="+incrementalPath)
		}
		ctr = ctr.WithExec(compilerEnvironment(a, cmd), noNesting())
		if a.Crate == opts.IncrementalCrate {
			// Retain a standalone native Directory result. Container.directory
			// is a transient projection whose runtime handle can disappear when
			// the session closes; withDirectory is a persistable operation.
			graph.Incremental = client.Directory().WithDirectory(".", ctr.Directory(incrementalPath))
		}
		op := Operation{Action: a, Container: ctr, Files: map[string]*dagger.File{}, Stamp: ctr.File(stampPath)}
		for _, filename := range a.Outputs {
			file := ctr.File(filename)
			op.Files[filename] = file
			dir := strings.TrimPrefix(path.Dir(filename), model.TargetRoot+"/")
			if dir == model.TargetRoot {
				dir = "."
			}
			artifacts[dir] = append(artifacts[dir], file)
		}
		byID[a.ID] = op
		graph.Operations = append(graph.Operations, op)
	}
	for _, dir := range sortedKeys(artifacts) {
		graph.Artifacts = graph.Artifacts.WithFiles(dir, artifacts[dir])
	}
	return graph, nil
}

// Keep environment values in the exec's cache identity without adding a
// container recipe step for every variable. Values are argv, never shell source.
// The pinned toolchain supplies GNU env, including its -u option.
func compilerEnvironment(a model.Action, command []string) []string {
	args := []string{"/usr/bin/env"}
	unset := map[string]bool{}
	for _, key := range a.UnsetEnv {
		args = append(args, "-u", key)
		unset[key] = true
	}
	args = append(args, "--")
	for _, key := range sortedKeys(a.Env) {
		if !unset[key] {
			args = append(args, key+"="+a.Env[key])
		}
	}
	return append(args, command...)
}

// Evaluate reads filesystem outputs only. Reading exec metadata (Sync/Stdout)
// could run a compiler again when only its filesystem was remotely transferred.
func (g *Graph) Evaluate(ctx context.Context, concurrency int) (*Report, error) {
	if concurrency < 1 {
		return nil, fmt.Errorf("concurrency must be positive")
	}
	started := time.Now()
	report := &Report{Actions: make([]ActionReport, len(g.Operations))}
	group, ctx := errgroup.WithContext(ctx)
	semaphore := make(chan struct{}, concurrency)
	done := map[string]chan struct{}{}
	for _, op := range g.Operations {
		done[op.Action.ID] = make(chan struct{})
	}
	var mutex sync.Mutex
	for i, op := range g.Operations {
		group.Go(func() error {
			for _, dep := range op.Action.Dependencies {
				select {
				case <-done[dep]:
				case <-ctx.Done():
					return ctx.Err()
				}
			}
			select {
			case semaphore <- struct{}{}:
			case <-ctx.Done():
				return ctx.Err()
			}
			defer func() { <-semaphore }()
			started := time.Now()
			marker, err := op.Stamp.Contents(ctx)
			if err != nil {
				return fmt.Errorf("compile %s: %w", op.Action.ID, err)
			}
			entry := ActionReport{ID: op.Action.ID, Crate: op.Action.Crate, Execution: strings.TrimSpace(marker), Digests: map[string]string{}}
			entry.DemandSeconds = time.Since(started).Seconds()
			started = time.Now()
			for _, filename := range sortedKeys(op.Files) {
				digest, err := op.Files[filename].Digest(ctx)
				if err != nil {
					return err
				}
				entry.Digests[filename] = digest
			}
			entry.DigestSeconds = time.Since(started).Seconds()
			mutex.Lock()
			report.Actions[i] = entry
			mutex.Unlock()
			close(done[op.Action.ID])
			return nil
		})
	}
	if err := group.Wait(); err != nil {
		return nil, err
	}
	report.ReplaySeconds = time.Since(started).Seconds()
	slices.SortFunc(report.Actions, func(a, b ActionReport) int { return strings.Compare(a.ID, b.ID) })
	return report, nil
}

func (r *Report) Reused(previous *Report) int {
	markers := map[string]string{}
	for _, action := range previous.Actions {
		markers[action.ID] = action.Execution
	}
	n := 0
	for _, action := range r.Actions {
		if action.Execution != "" && markers[action.ID] == action.Execution {
			n++
		}
	}
	return n
}
