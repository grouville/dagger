package engine

import (
	"fmt"
	"path"
	"strings"
)

// IsLiteralParentDirectoryTarget restricts the opt-in operation to the
// existing canonical filter pair whose old-client fallback names one path.
// Paths needing glob escaping and root itself continue using the old request.
func IsLiteralParentDirectoryTarget(target string) bool {
	return target != "" && target != "." && strings.TrimSpace(target) == target &&
		!strings.HasPrefix(target, "!") && !strings.HasPrefix(target, "/") &&
		!strings.HasPrefix(target, "../") && target != ".." &&
		!strings.ContainsAny(target, `*?[]^\`) && path.Clean(target) == target
}

// ValidateParentDirectoryMetadataRequest prevents the explicit operation
// from silently ignoring filters or other special filesync modes. The path is
// also checked with the host platform's filepath.IsLocal by the source FS.
func (o LocalImportOpts) ValidateParentDirectoryMetadataRequest() error {
	if !o.ParentDirsOnly {
		return fmt.Errorf("parent directory operation is not enabled")
	}
	if o.UseGitIgnore || o.FollowPaths != nil || o.ReadSingleFileOnly || o.MaxFileSize != 0 ||
		o.StatPathOnly || o.StatReturnAbsPath || o.StatResolvePath || o.GetAbsPathOnly ||
		o.GlobPattern != "" || o.SearchOpts != nil {
		return fmt.Errorf("parent directory operation cannot be combined with another filesync mode")
	}
	if len(o.IncludePatterns) != 1 || len(o.ExcludePatterns) != 1 ||
		!IsLiteralParentDirectoryTarget(o.IncludePatterns[0]) ||
		o.ExcludePatterns[0] != o.IncludePatterns[0]+"/*" {
		return fmt.Errorf("parent directory operation requires one literal target and its descendant exclusion")
	}
	return nil
}
