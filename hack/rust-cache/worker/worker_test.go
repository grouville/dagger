package worker

import (
	"reflect"
	"testing"

	"github.com/dagger/dagger/hack/rust-cache/model"
)

func TestMetadataAllowsLibraryButBinaryWaitsForTransitiveCodegen(t *testing.T) {
	a := model.Action{ID: "a", Outputs: []string{"a.rmeta"}}
	b := model.Action{ID: "b", Outputs: []string{"b.rmeta"}, Dependencies: []string{"a"}, Args: []string{"--extern", "a=a.rmeta"}}
	app := model.Action{ID: "app", Outputs: []string{"app"}, Dependencies: []string{"b"}}
	all := map[string]model.Action{"a": a, "b": b, "app": app}
	metadata := map[string]bool{"a": true, "b": true}
	complete := map[string]bool{"b": true}
	if !ready(b, all, complete, metadata, true) {
		t.Fatal("library could not start with metadata")
	}
	if ready(b, all, complete, metadata, false) {
		t.Fatal("disabled pipelining started before complete dependency")
	}
	if ready(app, all, complete, metadata, true) {
		t.Fatal("binary started before transitive machine code was ready")
	}
	complete["a"] = true
	if !ready(app, all, complete, metadata, true) {
		t.Fatal("binary could not start with complete dependencies")
	}
	delete(all, "a") // An exact result has already been mounted by the caller.
	delete(complete, "a")
	if !ready(b, all, complete, metadata, false) {
		t.Fatal("cached dependency unnecessarily delayed compiler")
	}
}

func TestExplicitRlibDoesNotStartWithOnlyMetadata(t *testing.T) {
	a := model.Action{ID: "a", Outputs: []string{"a.rmeta"}}
	b := model.Action{ID: "b", Outputs: []string{"b.rmeta"}, Dependencies: []string{"a"}, Args: []string{"--extern", "a=a.rlib"}}
	if ready(b, map[string]model.Action{"a": a}, nil, map[string]bool{"a": true}, true) {
		t.Fatal("an explicit rlib request started before machine code was ready")
	}
}

func TestNewInputsMustStayWithinPackageOwnership(t *testing.T) {
	action := model.Action{PackageRoot: "/src/app"}
	packages := []model.Package{{Root: "/src/app"}, {Root: "/src/app/nested"}, {Root: "/src/other"}}
	if err := validateInputs(action, packages, []string{"/src/app/src/main.rs", "/src/app/resource.txt"}); err != nil {
		t.Fatal(err)
	}
	for _, input := range []string{"/src/other/src/lib.rs", "/src/app2/resource.txt", "/src/app/nested/src/lib.rs", "/target/debug/deps/generated.rs"} {
		if err := validateInputs(action, packages, []string{input}); err == nil {
			t.Errorf("accepted source outside package ownership: %s", input)
		}
	}
}

func TestCompilerEnvironmentUsesAssignmentsAndRemovals(t *testing.T) {
	action := model.Action{Env: map[string]string{"NEW": "value with\nspaces", "REMOVE": "assigned"}, UnsetEnv: []string{"REMOVE"}}
	got := environment(action, []string{"PATH=/bin", "REMOVE=inherited", "NEW=previous"})
	want := []string{"NEW=value with\nspaces", "PATH=/bin"}
	if !reflect.DeepEqual(want, got) {
		t.Fatalf("compiler environment: %q", got)
	}
}
