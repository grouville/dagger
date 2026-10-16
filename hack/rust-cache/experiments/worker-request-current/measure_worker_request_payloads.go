// Measure the actual JSON representations, outside Dagger command timings.
package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path"
	"strings"

	"github.com/grouville/dagger-rust/compiler/model"
	"github.com/grouville/dagger-rust/compiler/worker"
)

func main() {
	for _, filename := range os.Args[1:] {
		data, err := os.ReadFile(filename)
		must(err)
		var plan model.Plan
		must(json.Unmarshal(data, &plan))
		root := "/src/app"
		for _, pkg := range plan.Packages {
			if strings.HasPrefix(path.Base(pkg.Root), "leaf_") && (root == "/src/app" || pkg.Root > root) {
				root = pkg.Root
			}
		}
		changed := map[string]bool{}
		for _, action := range plan.Actions {
			if action.PackageRoot == root {
				changed[action.ID] = true
			}
		}
		for progress := true; progress; {
			progress = false
			for _, action := range plan.Actions {
				if changed[action.ID] {
					continue
				}
				for _, dependency := range action.Dependencies {
					if changed[dependency] {
						changed[action.ID], progress = true, true
						break
					}
				}
			}
		}
		var missing []model.Action
		dependencies := make([]model.Action, len(plan.Actions))
		for i, action := range plan.Actions {
			if changed[action.ID] {
				missing = append(missing, action)
			}
			dependencies[i] = model.Action{ID: action.ID, Outputs: action.Outputs, Dependencies: action.Dependencies}
		}
		request := worker.Request{Actions: missing, Dependencies: plan.Actions, Packages: plan.Packages, Concurrency: 8, Pipelining: true}
		before, err := json.Marshal(request)
		must(err)
		request.Dependencies = dependencies
		after, err := json.Marshal(request)
		must(err)
		result := map[string]any{"plan": filename, "actions": len(plan.Actions), "changed_root": root, "executed_actions": len(missing), "request_bytes_before": len(before), "request_bytes_after": len(after)}
		encoded, err := json.Marshal(result)
		must(err)
		fmt.Println(string(encoded))
	}
}

func must(err error) {
	if err != nil {
		panic(err)
	}
}
