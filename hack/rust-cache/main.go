// rcexp records Cargo's compiler commands, then replays them through Dagger.
package main

import (
	"context"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"

	"dagger.io/dagger"
	"github.com/dagger/dagger/hack/rust-cache/model"
	"github.com/dagger/dagger/hack/rust-cache/replay"
	"github.com/dagger/dagger/internal/version"
)

type environmentFlags map[string]string

func (e environmentFlags) String() string { return "KEY=VALUE" }
func (e environmentFlags) Set(value string) error {
	key, val, ok := strings.Cut(value, "=")
	if !ok || key == "" {
		return errors.New("--env expects KEY=VALUE")
	}
	e[key] = val
	return nil
}

func main() {
	if err := run(context.Background(), os.Args[1:]); err != nil {
		fmt.Fprintln(os.Stderr, "rcexp:", err)
		os.Exit(1)
	}
}

func run(ctx context.Context, args []string) error {
	started := time.Now()
	if len(args) == 0 {
		return errors.New("usage: rcexp capture --source DIR --plan FILE [-- CARGO_BUILD_ARGS] | replay --source DIR --plan FILE --out DIR")
	}
	flags := flag.NewFlagSet(args[0], flag.ContinueOnError)
	sourcePath := flags.String("source", "", "path-only Cargo workspace")
	planPath := flags.String("plan", "", "captured plan JSON (outside the source directory)")
	image := flags.String("image", replay.DefaultImage, "capture toolchain image")
	outPath := flags.String("out", "", "replay artifact directory")
	reportPath := flags.String("report", "", "replay report JSON")
	previousPath := flags.String("previous", "", "previous report for counting reused operations")
	artifactsOnly := flags.Bool("artifacts-only", false, "export replay artifacts without collecting diagnostic markers or digests")
	incrementalCrate := flags.String("incremental-crate", "", "experimental: enable rustc incremental compilation for one crate")
	seedPath := flags.String("seed", "", "previous native incremental state JSON")
	statePath := flags.String("state", "", "write next native incremental state JSON")
	artifactLeafFiles := flags.Int("artifact-leaf-files", 0, "experimental: bound artifact-copy chains (0 keeps flat bundles)")
	artifactDirectories := flags.Bool("artifact-directories", false, "experimental: reuse whole compiler output snapshots")
	compilerConcurrency := flags.Int("compiler-concurrency", 0, "experimental: bound filesystem compiler demand (0 lets export demand the whole graph)")
	concurrency := flags.Int("concurrency", 8, "maximum concurrent diagnostic evaluation operations")
	env := environmentFlags{}
	flags.Var(env, "env", "capture environment input KEY=VALUE (repeatable)")
	if err := flags.Parse(args[1:]); err != nil {
		return err
	}
	if *sourcePath == "" || *planPath == "" {
		return errors.New("--source and --plan are required")
	}
	if args[0] != "capture" && args[0] != "replay" {
		return fmt.Errorf("unknown command %s", args[0])
	}
	if args[0] == "replay" && (len(flags.Args()) > 0 || len(env) > 0) {
		return errors.New("replay uses the recorded compiler configuration; recapture to change Cargo options or environment")
	}
	if *artifactsOnly && (args[0] != "replay" || *reportPath != "" || *previousPath != "") {
		return errors.New("--artifacts-only requires replay without --report or --previous")
	}
	if *concurrency < 1 {
		return errors.New("--concurrency must be positive")
	}
	if *artifactLeafFiles < 0 || *compilerConcurrency < 0 {
		return errors.New("--artifact-leaf-files and --compiler-concurrency must be nonnegative")
	}
	if *artifactDirectories && *artifactLeafFiles != 0 {
		return errors.New("--artifact-directories cannot be combined with --artifact-leaf-files")
	}
	if args[0] != "replay" && (*artifactLeafFiles != 0 || *compilerConcurrency != 0 || *artifactDirectories) {
		return errors.New("artifact and compiler concurrency experiments require replay")
	}
	if *incrementalCrate != "" || *seedPath != "" || *statePath != "" {
		if args[0] != "replay" || *incrementalCrate == "" || *statePath == "" {
			return errors.New("incremental experiment requires replay, --incremental-crate and --state")
		}
	}
	for _, output := range []string{*planPath, *outPath, *reportPath, *statePath, *seedPath} {
		if output == "" {
			continue
		}
		if err := outsideSource(*sourcePath, output); err != nil {
			return err
		}
	}
	phase := time.Now()
	source, err := replay.ReadSource(*sourcePath)
	if err != nil {
		return err
	}
	timings := &replay.DriverTimings{SourceSeconds: time.Since(phase).Seconds()}
	phase = time.Now()
	client, err := dagger.Connect(ctx, dagger.WithLogOutput(os.Stderr), dagger.WithVersionOverride(version.Version(version.WithV())))
	if err != nil {
		return err
	}
	defer client.Close()
	timings.ConnectSeconds = time.Since(phase).Seconds()
	switch args[0] {
	case "capture":
		wrapper, cleanup, err := buildWrapper(ctx)
		if err != nil {
			return err
		}
		defer cleanup()
		plan, err := replay.Capture(ctx, client, source, replay.CaptureOptions{Image: *image, Wrapper: client.Host().File(wrapper), CargoArgs: flags.Args(), Environment: env})
		if err != nil {
			return err
		}
		if err := writeJSON(*planPath, plan); err != nil {
			return err
		}
		fmt.Fprintf(os.Stderr, "captured %d compiler actions in %.3fs; plan: %s\n", len(plan.Actions), plan.CaptureSeconds, *planPath)
	case "replay":
		if *outPath == "" {
			return errors.New("--out is required for replay")
		}
		var plan model.Plan
		if err := readJSON(*planPath, &plan); err != nil {
			return err
		}
		phase = time.Now()
		opts := replay.BuildOptions{IncrementalCrate: *incrementalCrate, ArtifactLeafFiles: *artifactLeafFiles, ArtifactDirectories: *artifactDirectories}
		if *seedPath != "" {
			var seed replay.IncrementalState
			if err := readJSON(*seedPath, &seed); err != nil {
				return err
			}
			if err := seed.Validate(&plan, *incrementalCrate); err != nil {
				return err
			}
			opts.IncrementalSeed = dagger.Ref[*dagger.Directory](client, dagger.ID(seed.DirectoryID))
		}
		graph, err := replay.BuildWithOptions(client, &plan, source, opts)
		if err != nil {
			return err
		}
		timings.GraphSeconds = time.Since(phase).Seconds()
		if *compilerConcurrency != 0 {
			phase = time.Now()
			if err := graph.DemandFilesystem(ctx, *compilerConcurrency); err != nil {
				return err
			}
			timings.DemandSeconds = time.Since(phase).Seconds()
		}
		var report *replay.Report
		if !*artifactsOnly {
			report, err = graph.Evaluate(ctx, *concurrency)
			if err != nil {
				return err
			}
		}
		phase = time.Now()
		if _, err := graph.Artifacts.Export(ctx, *outPath); err != nil {
			return err
		}
		timings.ExportSeconds = time.Since(phase).Seconds()
		phase = time.Now()
		if graph.Incremental != nil {
			// Demand the filesystem part before publishing its ID. ID alone
			// need not materialize the state and would defer its cost to a later run.
			entries, err := graph.Incremental.Entries(ctx)
			if err != nil {
				return err
			}
			if len(entries) == 0 {
				return errors.New("rustc produced no incremental state")
			}
			id, err := graph.Incremental.ID(ctx)
			if err != nil {
				return err
			}
			compatibility, err := replay.SeedCompatibility(&plan, *incrementalCrate)
			if err != nil {
				return err
			}
			if err := writeJSON(*statePath, replay.IncrementalState{Version: 1, Crate: *incrementalCrate, Compatibility: compatibility, DirectoryID: string(id)}); err != nil {
				return err
			}
		}
		if graph.Incremental != nil {
			timings.IncrementalSeconds = time.Since(phase).Seconds()
		}
		timings.ReadySeconds = time.Since(started).Seconds()
		if *artifactsOnly {
			fmt.Fprintf(os.Stderr, "exported artifacts for %d compiler actions in %.3fs (shutdown excluded)\n", len(graph.Operations), timings.ReadySeconds)
			fmt.Fprintf(os.Stderr, "source %.3fs; connect %.3fs; graph %.3fs; demand %.3fs; export %.3fs; incremental state %.3fs\n", timings.SourceSeconds, timings.ConnectSeconds, timings.GraphSeconds, timings.DemandSeconds, timings.ExportSeconds, timings.IncrementalSeconds)
			return nil
		}
		report.Driver = timings
		if *reportPath == "" {
			*reportPath = *outPath + ".report.json"
		}
		if err := writeJSON(*reportPath, report); err != nil {
			return err
		}
		fmt.Fprintf(os.Stderr, "replayed %d compiler actions in %.3fs; capture time: %.3fs (excluded)\n", len(report.Actions), report.ReplaySeconds, plan.CaptureSeconds)
		fmt.Fprintf(os.Stderr, "source %.3fs; connect %.3fs; graph %.3fs; export %.3fs; artifacts ready %.3fs (shutdown excluded)\n", timings.SourceSeconds, timings.ConnectSeconds, timings.GraphSeconds, timings.ExportSeconds, timings.ReadySeconds)
		if *previousPath != "" {
			var previous replay.Report
			if err := readJSON(*previousPath, &previous); err != nil {
				return err
			}
			fmt.Fprintf(os.Stderr, "reused %d/%d compiler operations\n", report.Reused(&previous), len(report.Actions))
		}
	}
	return nil
}

func buildWrapper(ctx context.Context) (string, func(), error) {
	dir, err := os.MkdirTemp("", "rcexp-wrapper-")
	if err != nil {
		return "", nil, err
	}
	cleanup := func() { os.RemoveAll(dir) }
	filename := filepath.Join(dir, "rustc-wrapper")
	cmd := exec.CommandContext(ctx, "go", "build", "-trimpath", "-o", filename, "./hack/rust-cache/wrapper")
	cmd.Env = append(os.Environ(), "GOOS=linux", "GOARCH=amd64", "CGO_ENABLED=0")
	cmd.Stderr = os.Stderr
	if err := cmd.Run(); err != nil {
		cleanup()
		return "", nil, err
	}
	return filename, cleanup, nil
}

func outsideSource(source, filename string) error {
	source, err := filepath.Abs(source)
	if err != nil {
		return err
	}
	filename, err = filepath.Abs(filename)
	if err != nil {
		return err
	}
	rel, err := filepath.Rel(source, filename)
	if err != nil {
		return err
	}
	if rel != ".." && !strings.HasPrefix(rel, ".."+string(filepath.Separator)) {
		return fmt.Errorf("output %s must be outside the source directory", filename)
	}
	return nil
}

func readJSON(filename string, value any) error {
	data, err := os.ReadFile(filename)
	if err != nil {
		return err
	}
	return json.Unmarshal(data, value)
}

func writeJSON(filename string, value any) error {
	data, err := json.MarshalIndent(value, "", "  ")
	if err != nil {
		return err
	}
	if err := os.MkdirAll(filepath.Dir(filename), 0755); err != nil {
		return err
	}
	return os.WriteFile(filename, append(data, '\n'), 0600)
}
