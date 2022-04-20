package main

import (
	"net/http"
	_ "net/http/pprof"

	"github.com/pkg/profile"
	"go.dagger.io/dagger/cmd/dagger/cmd"
)

func main() {
	defer profile.Start(profile.MemProfile).Stop()
	go func() {
		http.ListenAndServe("localhost:8080", nil)
	}()
	cmd.Execute()
}
