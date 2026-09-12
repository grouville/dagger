//go:build ignore

// Publisher-side preparation through the existing Dagger compression API.
package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"time"

	"dagger.io/dagger"
)

var output string

const original = "rust@sha256:39f68a3e8e3ff425f8945ffa91128e60ff930d53e17fbb5214e95824bdd46f1b"

func main() {
	flag.StringVar(&output, "output-dir", "", "Existing fresh directory for the generated OCI artifact")
	flag.Parse()
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

func run() error {
	if output == "" || flag.NArg() != 0 {
		return fmt.Errorf("specify --output-dir")
	}
	info, err := os.Stat(output)
	if err != nil || !info.IsDir() {
		return fmt.Errorf("output directory is not accessible: %s", output)
	}
	output, err = filepath.Abs(output)
	if err != nil {
		return err
	}
	for _, file := range []string{"zstd.oci.tar", "build-image.json"} {
		if _, err := os.Lstat(output + "/" + file); !os.IsNotExist(err) {
			return fmt.Errorf("refuse existing/inaccessible output %s: %v", file, err)
		}
	}
	ctx := context.Background()
	client, err := dagger.Connect(ctx)
	if err != nil {
		return err
	}
	defer client.Close()
	base := client.Container(dagger.ContainerOpts{Platform: "linux/amd64"}).From(original)
	if _, err := base.Export(ctx, output+"/zstd.oci.tar", dagger.ContainerExportOpts{ForcedCompression: dagger.ImageLayerCompressionZstd}); err != nil {
		return err
	}
	record := map[string]any{
		"base_image": original, "platform": "linux/amd64", "forced_compression": "Zstd",
		"scope":     "Publisher-side export with existing Dagger API default level; not an end-user timing. No payload, toolchain, project, Cargo cache or configuration modification.",
		"completed": time.Now().UTC().Format(time.RFC3339Nano),
	}
	f, err := os.OpenFile(output+"/build-image.json", os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0644)
	if err != nil {
		return err
	}
	defer f.Close()
	enc := json.NewEncoder(f)
	enc.SetIndent("", "  ")
	return enc.Encode(record)
}
