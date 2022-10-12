package version

import (
	"errors"
	"runtime/debug"

	"github.com/moby/buildkit/identity"
)

var RandomGoModID string

// Initialize a global, random Buildkitd version for
// startGoModDaggerBuildkitd (go test)
func init() {
	RandomGoModID = identity.NewID()
}

var ErrNoBuildInfo = errors.New("no build info available")

// Revision returns the VCS revision being used to build or empty string
func Revision() (string, error) {
	bi, ok := debug.ReadBuildInfo()
	if !ok {
		return "", ErrNoBuildInfo
	}
	for _, s := range bi.Settings {
		if s.Key == "vcs.revision" {
			return s.Value[:9], nil
		}
	}
	return "", nil
}
