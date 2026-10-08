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

// packageSources assigns each file once, rather than scanning the whole workspace
// and every package root again for each compiler action. Nested packages own
// their files; a parent package must not depend on a nested package's source.
func (s Source) packageSources(packages []model.Package) map[string]Source {
	roots := newPackageRoots(packages)
	result := make(map[string]Source, len(packages))
	for name, file := range s {
		absolute := path.Join(model.SourceRoot, name)
		root := roots.owner(absolute)
		if root == "" {
			continue
		}
		if result[root] == nil {
			result[root] = Source{}
		}
		result[root][strings.TrimPrefix(absolute, root+"/")] = file
	}
	return result
}

type packageRoots map[string]struct{}

func newPackageRoots(packages []model.Package) packageRoots {
	roots := make(packageRoots, len(packages))
	for _, pkg := range packages {
		roots[pkg.Root] = struct{}{}
	}
	return roots
}

func (roots packageRoots) owner(filename string) string {
	// Walk toward /src so the most deeply nested package wins. This costs
	// directory depth, independently of the number of packages in the workspace.
	for candidate := path.Clean(filename); model.Within(model.SourceRoot, candidate); candidate = path.Dir(candidate) {
		if _, ok := roots[candidate]; ok {
			return candidate
		}
	}
	return ""
}
