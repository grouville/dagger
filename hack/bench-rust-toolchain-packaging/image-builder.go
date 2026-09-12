//go:build ignore

// Build normal OCI toolchain artifacts; no project sources or Cargo outputs.
package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"

	"dagger.io/dagger"
)

var output string

const baseImage = "rust@sha256:39f68a3e8e3ff425f8945ffa91128e60ff930d53e17fbb5214e95824bdd46f1b"
const toolchainConfig = "[toolchain]\nchannel = \"1.97.1\"\nprofile = \"minimal\"\ncomponents = [\"rustfmt\"]\n"

func main() {
	flag.StringVar(&output, "output-dir", "", "Fresh, exclusively owned directory for new OCI artifacts; no concurrent writers")
	flag.Parse()
	if err := build(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

func build() error {
	if output == "" || flag.NArg() != 0 {
		return fmt.Errorf("specify --output-dir pointing to an existing directory")
	}
	info, err := os.Stat(output)
	if err != nil || !info.IsDir() {
		return fmt.Errorf("output directory is not accessible: %s", output)
	}
	ctx := context.Background()
	for _, name := range []string{"base.oci.tar", "prepared.oci.tar", "build.json"} {
		if _, err := os.Lstat(filepath.Join(output, name)); !os.IsNotExist(err) {
			return fmt.Errorf("refuse existing or inaccessible output %s: %v", name, err)
		}
	}
	client, err := dagger.Connect(ctx)
	if err != nil {
		return err
	}
	defer client.Close()
	base := client.Container().From(baseImage)
	prepared := base.
		WithMountedFile("/tmp/rust-sync-libpopt.deb", client.HTTP("https://deb.debian.org/debian/pool/main/p/popt/libpopt0_1.19%2Bdfsg-1_amd64.deb", dagger.HTTPOpts{Checksum: "sha256:6f94b488255acd996254f775c77ff3956557c61f860a3c9caeaf65457554194f"})).
		WithMountedFile("/tmp/rust-sync-rsync.deb", client.HTTP("https://deb.debian.org/debian/pool/main/r/rsync/rsync_3.2.7-1%2Bdeb12u6_amd64.deb", dagger.HTTPOpts{Checksum: "sha256:ce99de6b36cbb62dc614a73463e467f2c1ef509545a9a2b33cab19b50530b672"})).
		WithExec([]string{"sh", "-c", "test \"$(dpkg --print-architecture)\" = amd64 && dpkg -i /tmp/rust-sync-libpopt.deb /tmp/rust-sync-rsync.deb"}).
		WithoutMount("/tmp/rust-sync-libpopt.deb").WithoutMount("/tmp/rust-sync-rsync.deb").
		WithWorkdir("/toolchain").
		WithMountedDirectory("/toolchain", client.Directory().WithNewFile("rust-toolchain.toml", toolchainConfig)).
		WithExec([]string{"rustup", "toolchain", "install", "--no-self-update"}).
		WithoutMount("/toolchain").WithWorkdir("/")
	checks := map[string]string{}
	for _, item := range []struct {
		name      string
		container *dagger.Container
		argv      []string
	}{
		{"base_rustc", base, []string{"rustc", "-vV"}},
		{"prepared_rustc", prepared, []string{"rustc", "-vV"}},
		{"base_cargo", base, []string{"cargo", "-V"}},
		{"prepared_cargo", prepared, []string{"cargo", "-V"}},
		{"base_cc", base, []string{"cc", "--version"}},
		{"prepared_cc", prepared, []string{"cc", "--version"}},
		{"base_components", base, []string{"rustup", "component", "list", "--installed"}},
		{"prepared_components", prepared, []string{"rustup", "component", "list", "--installed"}},
		{"prepared_rustfmt", prepared, []string{"rustfmt", "--version"}},
		{"prepared_sync_packages", prepared, []string{"dpkg-query", "-W", "rsync", "libpopt0"}},
	} {
		value, err := item.container.WithExec(item.argv).Stdout(ctx)
		if err != nil {
			return fmt.Errorf("%s: %w", item.name, err)
		}
		checks[item.name] = value
	}
	for _, name := range []string{"rustc", "cargo", "cc"} {
		if checks["base_"+name] != checks["prepared_"+name] {
			return fmt.Errorf("%s changed", name)
		}
	}
	if !strings.Contains(checks["prepared_components"], "rustfmt-x86_64-unknown-linux-gnu") {
		return fmt.Errorf("prepared image lacks requested rustfmt")
	}
	for _, item := range []struct {
		name      string
		container *dagger.Container
	}{{"base", base}, {"prepared", prepared}} {
		if _, err := item.container.Export(ctx, filepath.Join(output, item.name+".oci.tar")); err != nil {
			return err
		}
	}
	record := map[string]any{"base_image": baseImage, "toolchain_config": toolchainConfig, "checks": checks,
		"scope":     "Ordinary OCI packaging diagnostic; no Cargo project/cache/results included. Export is preparation, not a user timing.",
		"completed": time.Now().UTC().Format(time.RFC3339Nano)}
	file, err := os.OpenFile(filepath.Join(output, "build.json"), os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0644)
	if err != nil {
		return err
	}
	defer file.Close()
	encoder := json.NewEncoder(file)
	encoder.SetIndent("", "  ")
	return encoder.Encode(record)
}
