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

const stampPath = "/rcexp-execution"

type Operation struct {
	Action    model.Action
	Container *dagger.Container
	Files     map[string]*dagger.File
	Stamp     *dagger.File
}

type Graph struct {
	Operations []Operation
	Artifacts  *dagger.Directory
}

type ActionReport struct {
	ID        string            `json:"id"`
	Crate     string            `json:"crate"`
	Execution string            `json:"execution"`
	Digests   map[string]string `json:"digests"`
}

type Report struct {
	ReplaySeconds float64        `json:"replay_seconds"`
	Actions       []ActionReport `json:"actions"`
}

// Build creates only recipes. The caller chooses when and on which engine to demand them.
func Build(client *dagger.Client, plan *model.Plan, source Source) (*Graph, error) {
	if err := Validate(plan, source); err != nil {
		return nil, err
	}
	actions, err := ordered(plan.Actions)
	if err != nil {
		return nil, err
	}
	base := client.Container(dagger.ContainerOpts{Platform: "linux/amd64"}).From(plan.Image)
	graph := &Graph{Artifacts: client.Directory()}
	byID := map[string]Operation{}
	artifacts := map[string][]*dagger.File{}
	for _, a := range actions {
		ctr := base.WithMountedDirectory(a.PackageRoot, source.Package(client, a.PackageRoot, plan.Packages)).WithWorkdir(a.Cwd)
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
		for _, key := range sortedKeys(a.Env) {
			ctr = ctr.WithEnvVariable(key, a.Env[key])
		}
		for _, key := range a.UnsetEnv {
			ctr = ctr.WithoutEnvVariable(key)
		}
		// The nonce is an output, never an argument or a dependency input.
		cmd := []string{"sh", "-ec", "mkdir -p \"$1\"; shift; cat /proc/sys/kernel/random/uuid > " + stampPath + "; exec \"$@\"", "rcexp", model.Option(a.Args, "--out-dir"), a.Compiler}
		cmd = append(cmd, a.Args...)
		ctr = ctr.WithExec(cmd, noNesting())
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
			marker, err := op.Stamp.Contents(ctx)
			if err != nil {
				return fmt.Errorf("compile %s: %w", op.Action.ID, err)
			}
			entry := ActionReport{ID: op.Action.ID, Crate: op.Action.Crate, Execution: strings.TrimSpace(marker), Digests: map[string]string{}}
			for _, filename := range sortedKeys(op.Files) {
				digest, err := op.Files[filename].Digest(ctx)
				if err != nil {
					return err
				}
				entry.Digests[filename] = digest
			}
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
