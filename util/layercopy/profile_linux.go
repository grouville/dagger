//go:build linux

package layercopy

import (
	"io"
	"os"

	"golang.org/x/sys/unix"
)

func (p *CopyProfile) readDir(path string) ([]os.DirEntry, error) {
	defer p.measure("source.read_dir_call")()
	return os.ReadDir(path)
}

func (p *CopyProfile) stat(operation, path string) (os.FileInfo, error) {
	defer p.measure(operation)()
	return os.Stat(path)
}

func (p *CopyProfile) lstat(operation, path string) (os.FileInfo, error) {
	defer p.measure(operation)()
	return os.Lstat(path)
}

func (p *CopyProfile) rootPath(operation, root, path string, followFinalSymlink bool) (string, error) {
	defer p.measure(operation)()
	return rootPath(root, path, followFinalSymlink)
}

func (p *CopyProfile) mkdir(path string, mode os.FileMode) error {
	defer p.measure("destination.mkdir")()
	return os.Mkdir(path, mode)
}

func (p *CopyProfile) removeAll(path string) error {
	defer p.measure("destination.remove_all")()
	return os.RemoveAll(path)
}

func (p *CopyProfile) link(operation, source, destination string) error {
	defer p.measure(operation)()
	return os.Link(source, destination)
}

func (p *CopyProfile) open(path string) (*os.File, error) {
	defer p.measure("file.open")()
	return os.Open(path)
}

func (p *CopyProfile) create(path string) (*os.File, error) {
	defer p.measure("file.create")()
	return os.Create(path)
}

func (p *CopyProfile) copy(destination io.Writer, source io.Reader) (int64, error) {
	defer p.measure("file.copy")()
	n, err := io.Copy(destination, source)
	p.addBytes("file.copy", n)
	return n, err
}

func (p *CopyProfile) close(file *os.File) error {
	defer p.measure("file.close")()
	return file.Close()
}

func (p *CopyProfile) chown(path string, uid, gid int) error {
	defer p.measure("metadata.chown")()
	return os.Lchown(path, uid, gid)
}

func (p *CopyProfile) chmod(path string, mode os.FileMode) error {
	defer p.measure("metadata.chmod")()
	return os.Chmod(path, mode)
}

func (p *CopyProfile) utimes(path string, times []unix.Timespec) error {
	defer p.measure("metadata.utimes")()
	return unix.UtimesNanoAt(unix.AT_FDCWD, path, times, unix.AT_SYMLINK_NOFOLLOW)
}

func (p *CopyProfile) xattrs(destination, source string, userxattr bool, handler XAttrErrorHandler) error {
	defer p.measure("metadata.xattrs")()
	return copyXattrs(destination, source, userxattr, handler)
}
