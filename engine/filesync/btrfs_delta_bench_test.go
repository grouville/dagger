//go:build linux && composefsbench

package filesync

// Research-only: exercise native snapshots with verified manifest deltas. This
// is not wired into filesync, host change detection, or Dagger result ownership.

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"sort"
	"testing"
	"time"

	"github.com/dagger/dagger/engine/wcprof"
	"github.com/dagger/dagger/util/layercopy"
	"github.com/stretchr/testify/require"
)

type btrfsBenchDelta struct {
	remove []string
	write  []composeBenchNode
	dirs   []composeBenchNode
}

func btrfsBenchSame(a, b composeBenchNode) bool {
	return a.stat.Digest() == b.stat.Digest() && a.stat.ModTime().Equal(b.stat.ModTime()) &&
		(a.stat.IsDir() || a.stat.Size() == b.stat.Size()) && a.link == b.link
}

// Diff already-captured manifests. This O(N) in-memory pass is timed; obtaining
// these manifests is not. Renames deliberately use delete/add, not a supplied
// rename oracle. A future source protocol can provide trustworthy path deltas.
func btrfsBenchPlan(before, after []composeBenchNode) btrfsBenchDelta {
	old, next := map[string]composeBenchNode{}, map[string]composeBenchNode{}
	changed := map[string]bool{}
	groups := map[string]bool{}
	group := func(n composeBenchNode) string {
		if n.link != "" {
			return n.link
		}
		return n.name
	}
	for _, n := range before {
		old[n.name] = n
	}
	for _, n := range after {
		next[n.name] = n
	}
	for name, n := range old {
		if name == "" {
			continue
		}
		v, ok := next[name]
		if !ok || !btrfsBenchSame(n, v) {
			changed[name] = true
		}
	}
	for name, n := range next {
		if name == "" {
			continue
		}
		v, ok := old[name]
		if !ok || !btrfsBenchSame(n, v) {
			changed[name] = true
		}
	}
	// Recreate a whole affected alias group, so replacing the canonical name
	// cannot leave an unchanged alias pointing at the old version.
	for name := range changed {
		for _, entries := range []map[string]composeBenchNode{old, next} {
			if n, ok := entries[name]; ok && n.stat.Mode().IsRegular() {
				groups[group(n)] = true
			}
		}
	}
	for _, entries := range []map[string]composeBenchNode{old, next} {
		for name, n := range entries {
			if n.stat.Mode().IsRegular() && groups[group(n)] {
				changed[name] = true
			}
		}
	}
	d := btrfsBenchDelta{}
	dirtyDirs := map[string]bool{}
	for name := range changed {
		a, had := old[name]
		b, has := next[name]
		if had && !(has && a.stat.IsDir() && b.stat.IsDir()) {
			d.remove = append(d.remove, name)
		}
		if has {
			if b.stat.IsDir() {
				dirtyDirs[name] = true
			} else {
				d.write = append(d.write, b)
			}
		}
		for p := filepath.Dir(name); p != "."; p = filepath.Dir(p) {
			dirtyDirs[p] = true
		}
	}
	for name := range dirtyDirs {
		if n, ok := next[name]; ok && n.stat.IsDir() {
			d.dirs = append(d.dirs, n)
		}
	}
	sort.Sort(sort.Reverse(sort.StringSlice(d.remove)))
	sort.Slice(d.write, func(i, j int) bool { return d.write[i].name < d.write[j].name })
	sort.Slice(d.dirs, func(i, j int) bool { return d.dirs[i].name < d.dirs[j].name })
	return d
}

func btrfsBenchApply(ctx context.Context, source, dest string, d btrfsBenchDelta) error {
	for _, name := range d.remove {
		if err := ctx.Err(); err != nil {
			return err
		}
		if err := os.RemoveAll(filepath.Join(dest, name)); err != nil {
			return err
		}
	}
	for _, n := range d.dirs {
		if err := os.MkdirAll(filepath.Join(dest, n.name), 0o700); err != nil {
			return err
		}
	}
	for _, n := range d.write {
		if err := ctx.Err(); err != nil {
			return err
		}
		path := filepath.Join(dest, n.name)
		switch {
		case n.link != "":
			if err := os.Link(filepath.Join(dest, n.link), path); err != nil {
				return err
			}
		case n.stat.Mode()&os.ModeSymlink != 0:
			if err := os.Symlink(n.stat.Linkname, path); err != nil {
				return err
			}
			if err := rewriteMetadata(path, n.stat.Stat); err != nil {
				return err
			}
		case n.stat.Mode().IsRegular():
			f, err := os.OpenFile(path, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0o600)
			if err != nil {
				return err
			}
			err = writeCachedFile(f, filepath.Join(source, n.name), n.stat)
			_ = f.Close()
			if err != nil {
				return err
			}
		default:
			return fmt.Errorf("unsupported fixture node %s", n.name)
		}
	}
	// Child changes affect parent mtimes. Restore even otherwise-unchanged
	// ancestor metadata, bottom-up, using the synchronized manifest.
	for i := len(d.dirs) - 1; i >= 0; i-- {
		n := d.dirs[i]
		if err := rewriteMetadata(filepath.Join(dest, n.name), n.stat.Stat); err != nil {
			return err
		}
	}
	return nil
}

func btrfsBenchCommand(ctx context.Context, args ...string) error {
	out, err := exec.CommandContext(ctx, "btrfs", args...).CombinedOutput()
	if err != nil {
		return fmt.Errorf("btrfs %v: %w: %s", args, err, out)
	}
	return nil
}

func TestBtrfsDeltaMaterialize(t *testing.T) {
	source := os.Getenv("BTRFS_BENCH_SOURCE")
	if source == "" {
		t.Skip("requires an isolated Btrfs mount")
	}
	output, parent := os.Getenv("BTRFS_BENCH_OUT"), os.Getenv("BTRFS_BENCH_PARENT")
	require.True(t, filepath.IsAbs(source) && filepath.IsAbs(output))
	require.NoError(t, os.Mkdir(output, 0o755))
	ms := map[string]float64{}
	start := time.Now()
	after := composeBenchCapture(t, source)
	var before []composeBenchNode
	if parent != "" {
		before = composeBenchCapture(t, parent)
	}
	ms["input_capture"] = float64(time.Since(start)) / float64(time.Millisecond)
	ctx := context.Background()
	profile := os.Getenv("BTRFS_BENCH_PROFILE") == "1"
	if profile {
		wcprof.EnsureRecorder()
		ctx = wcprof.ContextWithProfiling(ctx)
	}
	ctx, root := wcprof.BeginOp(ctx, wcprof.OpKindIO, "btrfs.sample", wcprof.OpOpts{})
	defer func() {
		root.EndErr(nil)
		if profile {
			f, err := os.Create(filepath.Join(output, "wcprof.json"))
			require.NoError(t, err)
			require.NoError(t, wcprof.Active().WriteDump(f, true))
			require.NoError(t, f.Close())
		}
	}()
	phase := func(name string, fn func() error) {
		_, op := wcprof.BeginOp(ctx, wcprof.OpKindIO, "btrfs."+name, wcprof.OpOpts{})
		start := time.Now()
		err := fn()
		ms[name] = float64(time.Since(start)) / float64(time.Millisecond)
		op.EndErr(err)
		require.NoError(t, err)
	}
	result := filepath.Join(output, "result")
	start = time.Now()
	var d btrfsBenchDelta
	phase("plan", func() error { d = btrfsBenchPlan(before, after); return nil })
	phase("snapshot", func() error {
		if parent == "" {
			return btrfsBenchCommand(ctx, "subvolume", "create", result)
		}
		return btrfsBenchCommand(ctx, "subvolume", "snapshot", parent, result)
	})
	phase("apply", func() error {
		if parent != "" {
			return btrfsBenchApply(ctx, source, result, d)
		}
		c, err := layercopy.NewCopier(layercopy.Mount{Root: result})
		if err != nil {
			return err
		}
		err = c.CopyToEmpty(ctx, layercopy.Mount{Root: source}, "/", layercopy.CopyOptions{
			CopyDirContents: true, DisableSourceHardlinks: true, DisableXAttrs: true,
		}, nil)
		closeErr := c.Close()
		if err != nil {
			return err
		}
		return closeErr
	})
	phase("seal", func() error { return btrfsBenchCommand(ctx, "property", "set", "-ts", result, "ro", "true") })
	ms["ready"] = float64(time.Since(start)) / float64(time.Millisecond)
	phase("first_read_verify", func() error { composeBenchVerify(t, result, after); return nil })
	phase("second_read_verify", func() error { composeBenchVerify(t, result, after); return nil })
	if parent != "" {
		phase("old_version_verify", func() error { composeBenchVerify(t, parent, before); return nil })
	}
	// Both old and new snapshots are retained, matching the retained CAS arm.
	ms["ready_plus_first_read"] = ms["ready"] + ms["first_read_verify"]
	f, err := os.Create(filepath.Join(output, "result.json"))
	require.NoError(t, err)
	require.NoError(t, json.NewEncoder(f).Encode(map[string]any{
		"arm": "btrfs-delta", "case": os.Getenv("BTRFS_BENCH_CASE"), "ms": ms,
		"entries": len(after), "written": len(d.write), "removed": len(d.remove), "directories": len(d.dirs),
	}))
	require.NoError(t, f.Close())
}

func TestBtrfsDeltaPlanApply(t *testing.T) {
	// Applying the same plan to a private ordinary directory exercises delta
	// correctness without requiring mount privileges. Snapshot isolation is
	// separately checked against the retained parent in every Btrfs sample.
	source, dest := t.TempDir(), t.TempDir()
	require.NoError(t, os.Mkdir(filepath.Join(source, "dir"), 0o755))
	require.NoError(t, os.WriteFile(filepath.Join(source, "dir/a"), []byte("old"), 0o644))
	require.NoError(t, os.Link(filepath.Join(source, "dir/a"), filepath.Join(source, "dir/b")))
	require.NoError(t, os.WriteFile(filepath.Join(source, "gone"), []byte("gone"), 0o644))
	before := composeBenchCapture(t, source)
	require.NoError(t, btrfsBenchApply(t.Context(), source, dest, btrfsBenchPlan(nil, before)))
	composeBenchVerify(t, dest, before)
	require.NoError(t, os.WriteFile(filepath.Join(source, "dir/b"), []byte("new alias bytes"), 0o600))
	require.NoError(t, os.Remove(filepath.Join(source, "gone")))
	require.NoError(t, os.Symlink("dir/a", filepath.Join(source, "gone")))
	require.NoError(t, os.Mkdir(filepath.Join(source, "new"), 0o750))
	require.NoError(t, os.WriteFile(filepath.Join(source, "new/add"), []byte("added"), 0o640))
	after := composeBenchCapture(t, source)
	require.NoError(t, btrfsBenchApply(t.Context(), source, dest, btrfsBenchPlan(before, after)))
	composeBenchVerify(t, dest, after)
	require.NoError(t, os.Rename(filepath.Join(source, "dir"), filepath.Join(source, "new/moved")))
	moved := composeBenchCapture(t, source)
	require.NoError(t, btrfsBenchApply(t.Context(), source, dest, btrfsBenchPlan(after, moved)))
	composeBenchVerify(t, dest, moved)
}
