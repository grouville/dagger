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
