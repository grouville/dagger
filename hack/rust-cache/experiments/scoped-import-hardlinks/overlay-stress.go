package main

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"strings"

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
	client, err := daggerclient.Connect(ctx)
	if err != nil {
		return err
	}
	defer client.Close()
	query := core.NewQuery(client)
	repository, err := os.MkdirTemp("", "filesync-seed-overlay-")
	if err != nil {
		return err
	}
	defer os.RemoveAll(repository)
	if err := os.Mkdir(filepath.Join(repository, ".git"), 0755); err != nil {
		return err
	}
	root := filepath.Join(repository, "project")
	if err := os.Mkdir(root, 0755); err != nil {
		return err
	}
	files := map[string]string{".gitignore": "target/\nignored/\n!ignored/keep.txt\n", "target/drop": "ignored", "ignored/drop": "ignored too", "ignored/keep.txt": "included", "src/value": "initial", "keep": "unchanged", "remove": "removed later"}
	for name, value := range files {
		path := filepath.Join(root, name)
		if err := os.MkdirAll(filepath.Dir(path), 0755); err != nil {
			return err
		}
		if err := os.WriteFile(path, []byte(value), 0644); err != nil {
			return err
		}
	}
	if err := os.Symlink("src/value", filepath.Join(root, "link")); err != nil {
		return err
	}
	capture := func() (*core.Directory, error) {
		return query.Host().Directory(root, core.HostDirectoryOpts{NoCache: true, Gitignore: true}).Sync(ctx)
	}
	read := func(dir *core.Directory, name, want string) error {
		value, err := dir.File(name).Contents(ctx)
		if err != nil {
			return err
		}
		if value != want {
			return fmt.Errorf("%s: got %q, want %q", name, value, want)
		}
		return nil
	}
	original, err := capture()
	if err != nil {
		return err
	}
	previous, previousValue := original, "initial"
	for i := range 20 {
		value := fmt.Sprintf("edited-%03d-%s", i, strings.Repeat("x", i))
		if err := os.WriteFile(filepath.Join(root, "src/value"), []byte(value), 0644); err != nil {
			return err
		}
		if err := os.WriteFile(filepath.Join(root, "ignored/keep.txt"), []byte(value), 0644); err != nil {
			return err
		}
		if i == 5 {
			if err := os.Remove(filepath.Join(root, "remove")); err != nil {
				return err
			}
		}
		if i == 10 {
			if err := os.Link(filepath.Join(root, "src/value"), filepath.Join(root, "linked")); err != nil {
				return err
			}
		}
		if i == 15 {
			if err := os.Chmod(filepath.Join(root, "src/value"), 0640); err != nil {
				return err
			}
		}
		current, err := capture()
		if err != nil {
			return err
		}
		for _, name := range []string{"src/value", "link", "ignored/keep.txt"} {
			if err := read(current, name, value); err != nil {
				return fmt.Errorf("edit %d: %w", i, err)
			}
		}
		if err := read(current, "keep", "unchanged"); err != nil {
			return err
		}
		if err := read(original, "src/value", "initial"); err != nil {
			return fmt.Errorf("original changed at edit %d: %w", i, err)
		}
		if err := read(previous, "src/value", previousValue); err != nil {
			return fmt.Errorf("previous changed at edit %d: %w", i, err)
		}
		if i >= 10 {
			if err := read(current, "linked", value); err != nil {
				return err
			}
		}
		entries, err := current.Entries(ctx)
		if err != nil {
			return err
		}
		for _, name := range entries {
			if name == "target" || (i >= 5 && name == "remove") {
				return fmt.Errorf("edit %d contains excluded or removed entry %s", i, name)
			}
		}
		if i >= 15 {
			exported := filepath.Join(root, "../", filepath.Base(root)+"-export")
			if _, err := current.File("src/value").Export(ctx, exported); err != nil {
				return err
			}
			info, err := os.Stat(exported)
			os.Remove(exported)
			if err != nil {
				return err
			}
			if info.Mode().Perm() != 0640 {
				return fmt.Errorf("exported mode %o, want 640", info.Mode().Perm())
			}
		}
		previous, previousValue = current, value
	}
	fmt.Println("PASS: 20 real-overlay imports; current contents, old snapshots, ignored/re-included files, symlinks, hardlinks, deletion and permissions")
	return nil
}
