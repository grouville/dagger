package fsutil

import (
	"context"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"testing"
	"time"

	"github.com/dagger/dagger/internal/fsutil/types"
)

func BenchmarkSparseExportApply(b *testing.B) {
	for _, unrelated := range []int{0, 1000, 10000} {
		b.Run(fmt.Sprintf("Unrelated%d", unrelated), func(b *testing.B) {
			root := b.TempDir()
			if err := os.MkdirAll(filepath.Join(root, "unrelated"), 0755); err != nil {
				b.Fatal(err)
			}
			for i := 0; i < unrelated; i++ {
				if err := os.WriteFile(filepath.Join(root, "unrelated", fmt.Sprintf("file-%05d", i)), nil, 0644); err != nil {
					b.Fatal(err)
				}
			}
			for _, writes := range []int{1, 16} {
				b.Run(fmt.Sprintf("Write%d", writes), func(b *testing.B) {
					paths := make([]string, writes)
					for i := range paths {
						paths[i] = fmt.Sprintf("generated-%d", i)
					}
					st := &types.Stat{Mode: 0644, ModTime: time.Unix(1700000000, 0).UnixNano(), Uid: uint32(os.Getuid()), Gid: uint32(os.Getgid())}
					b.ReportAllocs()
					b.ResetTimer()
					for b.Loop() {
						dw, err := NewDiskWriter(context.Background(), root, DiskWriterOpt{SyncDataCb: func(_ context.Context, _ string, w io.WriteCloser) error {
							_, err := io.WriteString(w, "tiny generated content\n")
							return err
						}})
						if err != nil {
							b.Fatal(err)
						}
						for _, p := range paths {
							if err := dw.HandleChange(ChangeKindAdd, p, &StatInfo{st}, nil); err != nil {
								b.Fatal(err)
							}
						}
						if err := dw.Wait(context.Background()); err != nil {
							b.Fatal(err)
						}
					}
					b.StopTimer()
					for _, p := range paths {
						data, err := os.ReadFile(filepath.Join(root, p))
						if err != nil || string(data) != "tiny generated content\n" {
							b.Fatalf("bad exported bytes: %v", err)
						}
					}
				})
			}
		})
	}
}

func BenchmarkSparseDirectoryFinalization(b *testing.B) {
	for _, unrelated := range []int{0, 1000, 10000} {
		b.Run(fmt.Sprintf("Unrelated%d", unrelated), func(b *testing.B) {
			root := b.TempDir()
			if err := os.MkdirAll(filepath.Join(root, "unrelated"), 0755); err != nil {
				b.Fatal(err)
			}
			for i := 0; i < unrelated; i++ {
				if err := os.WriteFile(filepath.Join(root, "unrelated", fmt.Sprintf("file-%05d", i)), nil, 0644); err != nil {
					b.Fatal(err)
				}
			}
			for _, dirs := range []int{1, 16} {
				b.Run(fmt.Sprintf("Touched%d", dirs), func(b *testing.B) {
					dw, err := NewDiskWriter(context.Background(), root, DiskWriterOpt{SyncDataCb: func(context.Context, string, io.WriteCloser) error { return nil }})
					if err != nil {
						b.Fatal(err)
					}
					for i := 0; i < dirs; i++ {
						p := filepath.Join(root, "generated", fmt.Sprintf("dir-%d", i))
						if err := os.MkdirAll(p, 0755); err != nil {
							b.Fatal(err)
						}
						dw.dirModTimes[p] = time.Unix(1700000000, 0).UnixNano()
					}
					b.ReportAllocs()
					b.ResetTimer()
					for b.Loop() {
						if err := dw.Wait(context.Background()); err != nil {
							b.Fatal(err)
						}
					}
				})
			}
		})
	}
}
