package server

import (
	"context"
	"golang.org/x/sys/unix"
	"os"
)

// Hint the upcoming bulk scan before containerd takes its metadata write lock.
// The file is not parsed here: concurrent metadata writes remain protected by
// the collector's existing locking. Advisory failures leave collection intact.
func hintGCMetadata(ctx context.Context, path string) {
	file, err := os.Open(path)
	if err != nil {
		return
	}
	defer file.Close()
	stat, err := file.Stat()
	if err != nil {
		return
	}
	descriptor := int(file.Fd())
	const chunk = 64 << 10
	for offset := int64(0); offset < stat.Size(); offset += chunk {
		if ctx.Err() != nil {
			return
		}
		if unix.Fadvise(descriptor, offset, chunk, unix.FADV_WILLNEED) != nil {
			return
		}
	}
}
