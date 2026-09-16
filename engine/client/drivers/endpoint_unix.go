//go:build !windows

package drivers

import (
	"os"
	"syscall"
)

// privateDir reports whether path is a directory owned by the caller that
// nobody else can enter, following no symlink.
func privateDir(path string) bool {
	info, err := os.Lstat(path)
	if err != nil || !info.IsDir() || info.Mode().Perm()&0o077 != 0 {
		return false
	}
	st, ok := info.Sys().(*syscall.Stat_t)
	return ok && int(st.Uid) == os.Getuid()
}
