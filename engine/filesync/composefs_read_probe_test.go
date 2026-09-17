//go:build linux && composefsbench

package filesync

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"io/fs"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"testing"
	"time"

	"github.com/dagger/dagger/engine/wcprof"
	digest "github.com/opencontainers/go-digest"
	"github.com/stretchr/testify/require"
	"golang.org/x/sys/unix"
)

// This diagnostic reuses already verified, immutable benchmark results. It
// isolates filesystem consumption from admission/materialization and deliberately
// keeps the full semantic verifier outside the measured consumer.
func TestComposefsReadProbe(t *testing.T) {
	base := os.Getenv("COMPOSEFS_READ_BASE")
	if base == "" {
		t.Skip("requires retained materialization fixtures")
	}
	arm, mode := os.Getenv("COMPOSEFS_READ_ARM"), os.Getenv("COMPOSEFS_READ_MODE")
	output := os.Getenv("COMPOSEFS_READ_OUT")
	require.Contains(t, []string{"cas", "overlay", "composefs", "erofs"}, arm)
	require.Contains(t, []string{"none", "walkstat", "read", "original"}, mode)
	if arm == "erofs" {
		require.Contains(t, []string{"none", "walkstat"}, mode, "EROFS metadata alone has no payload bytes")
	}
	require.NoError(t, os.Mkdir(output, 0o755))
	nodes := composeBenchCapture(t, base)
	root := base
	wcprof.EnsureRecorder()
	ctx, op := wcprof.BeginOp(wcprof.ContextWithProfiling(context.Background()), wcprof.OpKindIO, "readprobe.sample", wcprof.OpOpts{})
	ms := map[string]float64{}
	work := map[string]float64{}
	measure := func(name string, fn func() error) {
		_, child := wcprof.BeginOp(ctx, wcprof.OpKindIO, "readprobe."+name, wcprof.OpOpts{})
		start := time.Now()
		err := fn()
		ms[name] = float64(time.Since(start)) / float64(time.Millisecond)
		child.EndErr(err)
		require.NoError(t, err)
	}
	defer func() {
		op.EndErr(nil)
		f, err := os.Create(filepath.Join(output, "wcprof.json"))
		require.NoError(t, err)
		require.NoError(t, wcprof.Active().WriteDump(f, true))
		require.NoError(t, f.Close())
	}()
	mounted := false
	if arm != "cas" {
		root = filepath.Join(output, "mount")
		require.NoError(t, os.Mkdir(root, 0o755))
		measure("mount", func() error {
			switch arm {
			case "composefs":
				out, err := exec.Command(os.Getenv("COMPOSEFS_BENCH_MOUNT"), "-o", "ro,basedir="+os.Getenv("COMPOSEFS_READ_CACHE"), os.Getenv("COMPOSEFS_READ_IMAGE"), root).CombinedOutput()
				if err != nil {
					return fmt.Errorf("mount: %w: %s", err, out)
				}
				return nil
			case "erofs":
				return unix.Mount(os.Getenv("COMPOSEFS_READ_IMAGE"), root, "erofs", unix.MS_RDONLY, "noacl")
			default:
				// A read-only overlay without an upper requires two lowers.
				empty := filepath.Join(output, "empty-lower")
				if err := os.Mkdir(empty, 0o755); err != nil {
					return err
				}
				return unix.Mount("overlay", root, "overlay", unix.MS_RDONLY, "lowerdir="+base+":"+empty)
			}
		})
		mounted = true
		defer func() {
			if mounted {
				require.NoError(t, unix.Unmount(root, 0))
			}
		}()
	}
	for pass := range 2 {
		if mode == "none" {
			break
		}
		var before, after runtime.MemStats
		runtime.ReadMemStats(&before)
		measure(fmt.Sprintf("read%d", pass+1), func() error {
			switch mode {
			case "walkstat":
				count := 0
				var statTime time.Duration
				err := filepath.WalkDir(root, func(path string, d fs.DirEntry, err error) error {
					if err != nil {
						return err
					}
					start := time.Now()
					_, err = d.Info()
					statTime += time.Since(start)
					count++
					return err
				})
				work[fmt.Sprintf("read%d_stat_ms", pass+1)] = float64(statTime) / float64(time.Millisecond)
				work[fmt.Sprintf("read%d_entries", pass+1)] = float64(count)
				// The raw metadata image also contains composefs's 00..ff
				// whiteouts. Only the composed view is a user-visible tree.
				if err == nil && arm != "erofs" && count != len(nodes) {
					return fmt.Errorf("entry count %d != %d", count, len(nodes))
				}
				return err
			case "read":
				buf := make([]byte, 32*1024)
				var openTime, readTime, closeTime time.Duration
				for _, n := range nodes {
					if !n.stat.Mode().IsRegular() {
						continue
					}
					h := newHashFromStat(n.stat.Stat)
					path := filepath.Join(root, n.name)
					start := time.Now()
					f, err := os.Open(path)
					openTime += time.Since(start)
					if err != nil {
						return err
					}
					start = time.Now()
					_, err = io.CopyBuffer(h, struct{ io.Reader }{f}, buf)
					readTime += time.Since(start)
					start = time.Now()
					closeErr := f.Close()
					closeTime += time.Since(start)
					if err != nil {
						return err
					}
					if closeErr != nil {
						return closeErr
					}
					if digest.NewDigest(n.stat.Digest().Algorithm(), h) != n.stat.Digest() {
						return fmt.Errorf("content mismatch: %s", n.name)
					}
				}
				work[fmt.Sprintf("read%d_open_ms", pass+1)] = float64(openTime) / float64(time.Millisecond)
				work[fmt.Sprintf("read%d_bytes_hash_ms", pass+1)] = float64(readTime) / float64(time.Millisecond)
				work[fmt.Sprintf("read%d_close_ms", pass+1)] = float64(closeTime) / float64(time.Millisecond)
				return nil
			default:
				composeBenchVerify(t, root, nodes)
				return nil
			}
		})
		runtime.ReadMemStats(&after)
		work[fmt.Sprintf("read%d_alloc_bytes", pass+1)] = float64(after.TotalAlloc - before.TotalAlloc)
		work[fmt.Sprintf("read%d_gc_cycles", pass+1)] = float64(after.NumGC - before.NumGC)
	}
	if mode != "none" && arm != "erofs" {
		measure("semantic_validation", func() error {
			composeBenchVerify(t, root, nodes)
			return nil
		})
	}
	if mounted {
		measure("unmount", func() error { return unix.Unmount(root, 0) })
		mounted = false
	}
	f, err := os.Create(filepath.Join(output, "result.json"))
	require.NoError(t, err)
	require.NoError(t, json.NewEncoder(f).Encode(map[string]any{"arm": arm, "mode": mode, "ms": ms, "work": work}))
	require.NoError(t, f.Close())
	t.Log(arm, mode, ms, work)
}
