package main

import (
	"context"
	"fmt"
	"os"
	"path/filepath"

	daggerclient "dagger.io/dagger"
	core "dagger.io/dagger/core"
)

func main() {
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

func run() error {
	ctx := context.Background()
	repository, err := os.MkdirTemp("", "scoped-hardlink-repro-")
	if err != nil {
		return err
	}
	defer os.RemoveAll(repository)
	for _, name := range []string{".git", "project"} {
		if err := os.Mkdir(filepath.Join(repository, name), 0755); err != nil {
			return err
		}
	}
	project := filepath.Join(repository, "project")
	primary := filepath.Join(project, "a-file")
	if err := os.WriteFile(primary, []byte("first contents"), 0644); err != nil {
		return err
	}
	if err := os.Link(primary, filepath.Join(project, "z-link")); err != nil {
		return err
	}
	client, err := daggerclient.Connect(ctx)
	if err != nil {
		return err
	}
	defer client.Close()
	query := core.NewQuery(client)
	for _, want := range []string{"first contents", "changed and longer contents"} {
		if err := os.WriteFile(primary, []byte(want), 0644); err != nil {
			return err
		}
		// The parent .git makes this a subdirectory import. noCache requests
		// another sync after the host edit; the old snapshot stays immutable.
		imported, err := query.Host().Directory(project, core.HostDirectoryOpts{Gitignore: true, NoCache: true}).Sync(ctx)
		if err != nil {
			return err
		}
		physical, err := os.ReadFile(filepath.Join(project, "z-link"))
		if err != nil {
			return err
		}
		if string(physical) != want {
			return fmt.Errorf("host hardlink did not change")
		}
		got, err := imported.File("z-link").Contents(ctx)
		if err != nil {
			return err
		}
		if got != want {
			return fmt.Errorf("imported hardlink: got %q, want %q", got, want)
		}
	}
	fmt.Println("PASS: edited scoped hardlink returns its current contents")
	return nil
}
