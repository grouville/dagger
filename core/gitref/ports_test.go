package gitref

import (
	"context"
	"testing"
)

func TestExplicitGitURLPreservesTransportPort(t *testing.T) {
	for _, clone := range []string{
		"http://localhost:8929/team/project.git",
		"https://git.example.org:8443/team/project.git",
		"ssh://git@git.example.org:2222/team/project.git",
	} {
		parsed, err := Parse(context.Background(), clone+"#main")
		if err != nil {
			t.Fatalf("Parse(%q): %v", clone, err)
		}
		if parsed.CloneRef != clone || parsed.SourceCloneRef != clone {
			t.Fatalf("Parse(%q) lost port: clone=%q, source=%q", clone, parsed.CloneRef, parsed.SourceCloneRef)
		}
	}
}

func TestExplicitGitURLModuleSubpath(t *testing.T) {
	const revision = "0123456789012345678901234567890123456789"
	for _, clone := range []string{
		"http://localhost:8929/team/project.git",
		"https://git.example.org:8443/team/project.git",
		"https://git.example.git:8443/team/project.git",
	} {
		parsed, err := Parse(context.Background(), clone+"/ci@"+revision)
		if err != nil {
			t.Fatalf("Parse(%q): %v", clone, err)
		}
		if parsed.CloneRef != clone || parsed.SourceCloneRef != clone || parsed.RepoRootSubdir != "ci" || parsed.ModVersion != revision {
			t.Fatalf("Parse(%q) lost repository boundary, port, subpath or revision: %+v", clone, parsed)
		}
	}
}
