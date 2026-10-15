package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"os"

	daggerclient "dagger.io/dagger"
	core "dagger.io/dagger/core"
	"github.com/dagger/querybuilder"
)

func main() {
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
func run() error {
	sourcePath := flag.String("source", "", "workspace path")
	image := flag.String("image", "rust:1.77-bookworm@sha256:83101f6985c93e1e6501b3375de188ee3d2cbb89968bcc91611591f9f447bd42", "toolchain image")
 nativeCache := flag.Bool("native-cache", false, "use the experimental native cache")
 cacheKey := flag.String("cache-key", "package-metadata-validation", "metadata cache namespace")
	flag.Parse()
	ctx := context.Background()
	client, err := daggerclient.Connect(ctx)
	if err != nil {
		return err
	}
	defer client.Close()
	base := querybuilder.Query().Client(client.GraphQLClient())
	var served bool
	if err := base.Select("serveModule").Arg("address", ".").Bind(&served).Execute(ctx); err != nil {
		return err
	}
	source := core.NewQuery(client).Host().Directory(*sourcePath, core.HostDirectoryOpts{Exclude: []string{".git", "target", "dagger.toml", "dagger.lock"}})
	id, err := source.ID(ctx)
	if err != nil {
		return err
	}
	var state string
	if err := base.Select("rust").Arg("image", *image).Arg("locked", true).Arg("nativeCache", *nativeCache).Arg("cacheKey", *cacheKey).Select("serializedProject").Arg("source", id).Bind(&state).Execute(ctx); err != nil {
		return err
	}
	return json.NewEncoder(os.Stdout).Encode(state)
}
