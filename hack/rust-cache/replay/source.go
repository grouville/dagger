package replay

import (
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"io/fs"
	"os"
	"path"
	"path/filepath"
	"sort"
	"strings"
	"unicode/utf8"

	"dagger.io/dagger"
	"github.com/dagger/dagger/hack/rust-cache/model"
)

type SourceFile struct {
	Contents string
	Mode     int
}

// Source is a content snapshot, independent of host/session directory handles.
type Source map[string]SourceFile

func ReadSource(root string) (Source, error) {
	files := Source{}
	err := filepath.WalkDir(root, func(filename string, entry fs.DirEntry, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		rel, err := filepath.Rel(root, filename)
		if err != nil {
			return err
		}
		if entry.IsDir() {
			if rel != "." && (entry.Name() == "target" || entry.Name() == ".git") {
				return filepath.SkipDir
			}
			return nil
		}
		info, err := entry.Info()
		if err != nil {
			return err
		}
		if !info.Mode().IsRegular() {
			return fmt.Errorf("unsupported source file %s: only regular files are supported", rel)
		}
		contents, err := os.ReadFile(filename)
		if err != nil {
			return err
		}
		if !utf8.Valid(contents) {
			return fmt.Errorf("unsupported binary source resource %s: this experiment currently accepts UTF-8 files", rel)
		}
		files[filepath.ToSlash(rel)] = SourceFile{Contents: string(contents), Mode: int(info.Mode().Perm())}
		return nil
	})
	return files, err
}

func (s Source) ConfigDigest() string {
	hash := sha256.New()
	for _, name := range s.names() {
		base := path.Base(name)
		if base != "Cargo.toml" && base != "Cargo.lock" && base != "rust-toolchain" && base != "rust-toolchain.toml" && !strings.Contains("/"+name, "/.cargo/") {
			continue
		}
		file := s[name]
		fmt.Fprintf(hash, "%s\x00%d\x00%d\x00", name, file.Mode, len(file.Contents))
		hash.Write([]byte(file.Contents))
	}
	return hex.EncodeToString(hash.Sum(nil))
}

func (s Source) names() []string {
	names := make([]string, 0, len(s))
	for name := range s {
		names = append(names, name)
	}
	sort.Strings(names)
	return names
}

func (s Source) Directory(client *dagger.Client) *dagger.Directory {
	dir := client.Directory()
	for _, name := range s.names() {
		file := s[name]
		dir = dir.WithNewFile(name, file.Contents, dagger.DirectoryWithNewFileOpts{Permissions: file.Mode})
	}
	return dir
}

func (s Source) Package(client *dagger.Client, root string, packages []model.Package) *dagger.Directory {
	dir := client.Directory()
	for _, name := range s.names() {
		absolute := path.Join(model.SourceRoot, name)
		if owner(packages, absolute) != root {
			continue
		}
		rel := strings.TrimPrefix(strings.TrimPrefix(absolute, root), "/")
		file := s[name]
		dir = dir.WithNewFile(rel, file.Contents, dagger.DirectoryWithNewFileOpts{Permissions: file.Mode})
	}
	return dir
}

func owner(packages []model.Package, filename string) string {
	var root string
	for _, pkg := range packages {
		if model.Within(pkg.Root, filename) && len(pkg.Root) > len(root) {
			root = pkg.Root
		}
	}
	return root
}
