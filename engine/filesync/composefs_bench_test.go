//go:build linux && composefsbench

package filesync

// This opt-in materializer experiment deliberately changes no engine behavior.
// See hack/bench/composefs/README.md for its narrower-than-filesync boundary.

import (
	"bufio"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"io/fs"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"syscall"
	"testing"
	"time"

	"github.com/dagger/dagger/engine/wcprof"
	fstypes "github.com/dagger/dagger/internal/fsutil/types"
	"github.com/dagger/dagger/util/hashutil"
	"github.com/dagger/dagger/util/layercopy"
	digest "github.com/opencontainers/go-digest"
	"github.com/stretchr/testify/require"
	"golang.org/x/sys/unix"
)

type composeBenchNode struct {
	name string
	stat *HashedStatInfo
	unix *syscall.Stat_t
	link string // Genuine source hardlink, not content deduplication.
}

type composeBenchResult struct {
	Arm          string                 `json:"arm"`
	Case         string                 `json:"case"`
	Profiled     bool                   `json:"profiled"`
	Entries      int                    `json:"entries"`
	Bytes        int64                  `json:"bytes"`
	ImageBytes   int64                  `json:"image_bytes,omitempty"`
	Ingested     int                    `json:"ingested"`
	Milliseconds map[string]float64     `json:"ms"`
	Copy         *layercopy.CopyProfile `json:"copy,omitempty"`
}

// TestComposefsMaterialize runs one sample. Stores may persist between samples,
// but the output directory must be new. All mounts are private to the caller's
// mount namespace. The harness runs this in an isolated short-lived container.
func TestComposefsMaterialize(t *testing.T) {
	source := os.Getenv("COMPOSEFS_BENCH_SOURCE")
	if source == "" {
		t.Skip("set COMPOSEFS_BENCH_SOURCE to run the external-tool experiment")
	}
	arm, cacheRoot, output := os.Getenv("COMPOSEFS_BENCH_ARM"), os.Getenv("COMPOSEFS_BENCH_CACHE"), os.Getenv("COMPOSEFS_BENCH_OUT")
	require.Contains(t, []string{"cas", "composefs"}, arm)
	for _, path := range []string{source, cacheRoot, output} {
		require.True(t, filepath.IsAbs(path), "use absolute paths")
	}
	require.NoError(t, os.Mkdir(output, 0o755), "each sample needs a new output directory")
	require.NoError(t, os.MkdirAll(cacheRoot, 0o755))

	// Shared input preparation stands in for the already-synchronized manifest.
	// It is reported, not mislabelled as the real client scan or included in the
	// materialization comparison. It reads the same source before either arm.
	started := time.Now()
	nodes := composeBenchCapture(t, source)
	r := composeBenchResult{Arm: arm, Case: os.Getenv("COMPOSEFS_BENCH_CASE"), Profiled: os.Getenv("COMPOSEFS_BENCH_PROFILE") != "0", Entries: len(nodes), Milliseconds: map[string]float64{}}
	r.Milliseconds["input_capture"] = float64(time.Since(started)) / float64(time.Millisecond)
	for _, n := range nodes {
		if n.stat.Mode().IsRegular() {
			r.Bytes += n.stat.Size()
		}
	}

	ctx := context.Background()
	if r.Profiled {
		wcprof.EnsureRecorder()
		ctx = wcprof.ContextWithProfiling(ctx)
	}
	ctx, rootOp := wcprof.BeginOp(ctx, wcprof.OpKindIO, "materializer.sample", wcprof.OpOpts{})
	t.Cleanup(func() {
		if !r.Profiled {
			return
		}
		var sampleErr error
		if t.Failed() {
			sampleErr = fmt.Errorf("sample failed")
		}
		rootOp.EndErr(sampleErr)
		f, err := os.Create(filepath.Join(output, "wcprof.json"))
		require.NoError(t, err)
		require.NoError(t, wcprof.Active().WriteDump(f, true))
		require.NoError(t, f.Close())
	})
	phase := func(name string, fn func(context.Context)) {
		c, op := wcprof.BeginOp(ctx, wcprof.OpKindIO, "materializer."+name, wcprof.OpOpts{})
		start := time.Now()
		defer func() {
			r.Milliseconds[name] = float64(time.Since(start)) / float64(time.Millisecond)
			op.EndErr(nil)
		}()
		fn(c)
	}

	resultPath := filepath.Join(output, "result")
	mounted := false
	started = time.Now()
	require.NoError(t, os.Mkdir(resultPath, 0o755))
	if arm == "cas" {
		phase("copy_and_publish", func(ctx context.Context) {
			local, err := newLocalFS(NewMirrorSharedStateWithFileCache(source, cacheRoot), "", nil, nil, nil, "")
			require.NoError(t, err)
			changes := make([]CachedChange, 0, len(nodes))
			for _, n := range nodes {
				if n.link == "" {
					changes = append(changes, &cachedChange{callKey: n.name, val: &ChangeWithStat{kind: ChangeKindNone, stat: n.stat}})
				}
			}
			cache := local.newFileCacheCopy(ctx, changes)
			copier, err := layercopy.NewCopier(layercopy.Mount{Root: resultPath})
			require.NoError(t, err)
			if r.Profiled {
				r.Copy = &layercopy.CopyProfile{}
			}
			err = copier.CopyToEmpty(ctx, layercopy.Mount{Root: source}, "/", layercopy.CopyOptions{
				CopyDirContents: true, DisableSourceHardlinks: true, DisableXAttrs: true,
				ImmutableFileSource: cache.lookup, Profile: r.Copy,
			}, cache.materialize)
			closeErr := copier.Close()
			require.NoError(t, err)
			require.NoError(t, closeErr)
			r.Ingested = len(cache.candidates)
			require.NoError(t, cache.publish(ctx))
		})
	} else {
		phase("cas_admission", func(ctx context.Context) {
			for _, n := range nodes {
				if !n.stat.Mode().IsRegular() || n.link != "" || n.stat.Size() == 0 {
					continue
				}
				key := fileCacheKey(n.stat)
				path := fileCachePath(cacheRoot, key)
				hit, err := lookupCachedFile(path, key, n.stat)
				require.NoError(t, err)
				if hit != "" {
					continue
				}
				// Same verified writer and atomic no-replace publication as the
				// inode CAS. No destination tree exists to ingest into in this arm.
				_, op := wcprof.BeginOp(ctx, wcprof.OpKindIO, "materializer.ingest", wcprof.OpOpts{})
				require.NoError(t, os.MkdirAll(filepath.Dir(path), 0o700))
				f, err := os.CreateTemp(filepath.Dir(path), ".ingest-")
				require.NoError(t, err)
				err = writeCachedFile(f, filepath.Join(source, n.name), n.stat)
				if err == nil {
					err = os.Link(f.Name(), path)
					if os.IsExist(err) {
						err = nil
					}
				}
				_ = f.Close()
				removeErr := os.Remove(f.Name())
				op.EndErr(err)
				require.NoError(t, err)
				require.NoError(t, removeErr)
				r.Ingested++
			}
		})
		imagePath := filepath.Join(output, "tree.cfs")
		phase("encode", func(context.Context) {
			f, err := os.Create(filepath.Join(output, "tree.dump"))
			require.NoError(t, err)
			w := bufio.NewWriter(f)
			for _, n := range nodes {
				payload, mode := "-", fmt.Sprintf("%o", n.unix.Mode)
				switch {
				case n.link != "":
					mode, payload = "@"+mode, composeBenchEscape("/"+n.link)
				case n.stat.Mode()&os.ModeSymlink != 0:
					payload = composeBenchEscape(n.stat.Linkname)
				case n.stat.Mode().IsRegular() && n.stat.Size() > 0:
					rel, err := filepath.Rel(cacheRoot, fileCachePath(cacheRoot, fileCacheKey(n.stat)))
					require.NoError(t, err)
					payload = composeBenchEscape(rel)
				}
				_, err := fmt.Fprintf(w, "%s %d %s %d %d %d %d %d.%09d %s - -\n",
					composeBenchEscape("/"+n.name), n.stat.Size(), mode, n.unix.Nlink,
					n.stat.Uid, n.stat.Gid, n.unix.Rdev, n.stat.ModTime().Unix(), n.stat.ModTime().Nanosecond(), payload)
				require.NoError(t, err)
			}
			require.NoError(t, w.Flush())
			require.NoError(t, f.Close())
		})
		phase("image", func(ctx context.Context) {
			out, err := exec.CommandContext(ctx, os.Getenv("COMPOSEFS_BENCH_MK"), "--from-file", "--max-version=1", filepath.Join(output, "tree.dump"), imagePath).CombinedOutput()
			require.NoError(t, err, "%s", out)
		})
		info, err := os.Stat(imagePath)
		require.NoError(t, err)
		r.ImageBytes = info.Size()
		phase("mount", func(ctx context.Context) {
			out, err := exec.CommandContext(ctx, os.Getenv("COMPOSEFS_BENCH_MOUNT"), "-o", "ro,basedir="+cacheRoot, imagePath, resultPath).CombinedOutput()
			require.NoError(t, err, "%s", out)
		})
		mounted = true
		// Payload storage stays alive until after this unmount. A container
		// namespace also confines mounts if a test process fails unexpectedly.
		t.Cleanup(func() {
			if mounted {
				require.NoError(t, unix.Unmount(resultPath, 0))
			}
		})
	}
	r.Milliseconds["ready"] = float64(time.Since(started)) / float64(time.Millisecond)
	// Include an actual consumer. A mount-only win can otherwise move all work
	// to lookup/read. Each pass verifies bytes and supported semantic metadata.
	phase("first_read_verify", func(context.Context) { composeBenchVerify(t, resultPath, nodes) })
	phase("second_read_verify", func(context.Context) { composeBenchVerify(t, resultPath, nodes) })
	if mounted {
		phase("unmount", func(context.Context) {
			require.NoError(t, unix.Unmount(resultPath, 0))
			mounted = false
		})
	}
	r.Milliseconds["ready_plus_first_read"] = r.Milliseconds["ready"] + r.Milliseconds["first_read_verify"]
	r.Milliseconds["ready_first_read_release"] = r.Milliseconds["ready_plus_first_read"] + r.Milliseconds["unmount"]
	r.Milliseconds["ready_two_reads_release"] = float64(time.Since(started)) / float64(time.Millisecond)
	f, err := os.Create(filepath.Join(output, "result.json"))
	require.NoError(t, err)
	enc := json.NewEncoder(f)
	enc.SetIndent("", "  ")
	require.NoError(t, enc.Encode(r))
	require.NoError(t, f.Close())
	t.Logf("%s %s: ready %.2f ms, first full read+verify %.2f ms", r.Arm, r.Case, r.Milliseconds["ready"], r.Milliseconds["first_read_verify"])
}

func composeBenchCapture(t *testing.T, root string) []composeBenchNode {
	t.Helper()
	var nodes []composeBenchNode
	links := map[[2]uint64]string{}
	require.NoError(t, filepath.WalkDir(root, func(path string, entry fs.DirEntry, err error) error {
		if err != nil {
			return err
		}
		rel, err := filepath.Rel(root, path)
		require.NoError(t, err)
		if rel == "." {
			rel = ""
		}
		info, err := entry.Info()
		require.NoError(t, err)
		u := info.Sys().(*syscall.Stat_t)
		st := &fstypes.Stat{Path: rel, Mode: uint32(info.Mode()), Uid: u.Uid, Gid: u.Gid, ModTime: info.ModTime().UnixNano()}
		if !info.IsDir() {
			st.Size_ = info.Size()
		}
		if info.Mode()&os.ModeSymlink != 0 {
			st.Linkname, err = os.Readlink(path)
			require.NoError(t, err)
		}
		h := newHashFromStat(st)
		if info.Mode().IsRegular() {
			f, err := os.Open(path)
			require.NoError(t, err)
			_, err = io.Copy(h, f)
			require.NoError(t, err)
			require.NoError(t, f.Close())
		} else {
			require.True(t, info.IsDir() || info.Mode()&os.ModeSymlink != 0, "unsupported fixture node: %s", path)
		}
		n := composeBenchNode{name: rel, unix: u, stat: &HashedStatInfo{StatInfo: StatInfo{st}, dgst: digest.NewDigest(hashutil.XXH3, h)}}
		if info.Mode().IsRegular() {
			id := [2]uint64{u.Dev, u.Ino}
			n.link = links[id]
			if n.link == "" {
				links[id] = rel
			}
		}
		nodes = append(nodes, n)
		return nil
	}))
	return nodes
}

func composeBenchVerify(t *testing.T, root string, expected []composeBenchNode) {
	t.Helper()
	actual := composeBenchCapture(t, root)
	require.Len(t, actual, len(expected))
	for i, want := range expected {
		got := actual[i]
		require.Equal(t, want.name, got.name)
		if want.name == "" {
			// CopyDirContents imports children, not the source root inode.
			require.True(t, got.stat.IsDir())
			continue
		}
		require.Equal(t, want.stat.Digest(), got.stat.Digest(), "bytes/type/mode/owner/link target: %s", want.name)
		require.Equal(t, want.stat.ModTime(), got.stat.ModTime(), "mtime: %s", want.name)
		if !want.stat.IsDir() {
			require.Equal(t, want.stat.Size(), got.stat.Size(), "size: %s", want.name)
		}
		require.Equal(t, want.link, got.link, "hardlink grouping: %s", want.name)
	}
}

func composeBenchEscape(value string) string {
	var b strings.Builder
	for i := range len(value) {
		c := value[i]
		if c <= ' ' || c >= 127 || c == '\\' || value == "-" {
			fmt.Fprintf(&b, "\\x%02x", c)
		} else {
			b.WriteByte(c)
		}
	}
	return b.String()
}

func TestComposefsDumpEscape(t *testing.T) {
	require.Equal(t, `/a\x20b\x0a\x5c\xff`, composeBenchEscape("/a b\n\\\xff"))
	require.Equal(t, `\x2d`, composeBenchEscape("-"))
}
