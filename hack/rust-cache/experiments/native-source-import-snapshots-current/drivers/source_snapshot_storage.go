package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"time"

	daggerclient "dagger.io/dagger"
	"dagger.io/dagger/core"
)

type capture struct {
	Edit int     `json:"edit"`
	ID   core.ID `json:"id"`
}

func main() {
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

func run() error {
	source := flag.String("source", "", "source fixture")
	output := flag.String("output", "", "directory IDs for storage inspection")
	edits := flag.Int("edits", 19, "fresh imports, including the initial import")
	hold := flag.String("hold-file", "", "keep result owners alive until this file exists")
	flag.Parse()
	if *source == "" || *output == "" {
		return fmt.Errorf("source and output are required")
	}
	ctx := context.Background()
	client, err := daggerclient.Connect(ctx)
	if err != nil {
		return err
	}
	defer client.Close()
	query := core.NewQuery(client)
	filename := filepath.Join(*source, "leaf_1023/src/lib.rs")
	original, err := os.ReadFile(filename)
	if err != nil {
		return err
	}
	pattern := regexp.MustCompile(`pub const EDIT: u64 = \d+;`)
	if len(pattern.FindAll(original, -1)) != 1 {
		return fmt.Errorf("expected one used edit")
	}
	var first *core.Directory
	var firstValue string
	var captures []capture
	for i := range *edits {
		contents := pattern.ReplaceAllString(string(original), fmt.Sprintf("pub const EDIT: u64 = %d;", 800000000000+i))
		if err := os.WriteFile(filename, []byte(contents), 0644); err != nil {
			return err
		}
		dir, err := query.Host().Directory(*source, core.HostDirectoryOpts{NoCache: true, Exclude: []string{".git", "target", "dagger.toml", "dagger.lock"}}).Sync(ctx)
		if err != nil {
			return err
		}
		value, err := dir.File("leaf_1023/src/lib.rs").Contents(ctx)
		if err != nil {
			return err
		}
		if value != contents {
			return fmt.Errorf("edit %d returned stale contents", i)
		}
		if first == nil {
			first, firstValue = dir, value
		}
		old, err := first.File("leaf_1023/src/lib.rs").Contents(ctx)
		if err != nil {
			return err
		}
		if old != firstValue {
			return fmt.Errorf("edit %d changed the original snapshot", i)
		}
		id, err := dir.ID(ctx)
		if err != nil {
			return err
		}
		captures = append(captures, capture{Edit: i, ID: id})
	}
	encoded, err := json.MarshalIndent(captures, "", "  ")
	if err != nil {
		return err
	}
	if err := os.WriteFile(*output, append(encoded, '\n'), 0644); err != nil {
		return err
	}
	fmt.Printf("PASS: %d imports and unchanged original snapshot\n", len(captures))
	if *hold != "" {
		for {
			_, err := os.Stat(*hold)
			if err == nil {
				break
			}
			if !os.IsNotExist(err) {
				return err
			}
			time.Sleep(100 * time.Millisecond)
		}
	}
	return nil
}
