package dang

import (
	"context"
	"os"
	"path/filepath"

	"github.com/Khan/genqlient/graphql"
)

// BindGraphQLClient binds a context-dependent client when a runtime value is
// created. Prepared functions keep the unbound client; their returned values
// belong to the current invocation, including serialization of lazy IDs.
func BindGraphQLClient(ctx context.Context, client graphql.Client) graphql.Client {
	if binder, ok := client.(interface {
		BindContext(context.Context) graphql.Client
	}); ok {
		return binder.BindContext(ctx)
	}
	return client
}

// ReusableDirectoryDeclarations is a diagnostic gate for sharing an evaluated
// directory's declarations. It accepts only object declarations without static
// initializers or nested type declarations. These create constructors and
// closures, but evaluate no program expressions at directory initialization.
//
// Callers must separately preserve source/schema identity and source paths,
// and bind GraphQL clients at invocation time. This does not make arbitrary
// RunDir results reusable.
func ReusableDirectoryDeclarations(ctx context.Context, dir string) (bool, error) {
	// Native imports may initialize values or resolve dependencies outside this
	// directory. Keep their existing per-invocation behavior.
	if _, err := os.Stat(filepath.Join(dir, "dang.toml")); err == nil {
		return false, nil
	} else if !os.IsNotExist(err) {
		return false, err
	}
	_, blocks, err := parseDirBlocks(ctx, dir)
	if err != nil {
		return false, err
	}
	if len(blocks) == 0 {
		return false, nil
	}
	for _, block := range blocks {
		for _, form := range block.Forms {
			object, ok := form.(*ObjectDecl)
			if !ok {
				return false, nil
			}
			safe := true
			object.Walk(func(node Node) bool {
				if node == object {
					return true
				}
				switch node.(type) {
				case *ObjectDecl, *ScalarDecl, *EnumDecl, *InterfaceDecl, *UnionDecl,
					*SelfBlockDecl, *ImportDecl, *DirectiveDecl:
					safe = false
					return false
				}
				return safe
			})
			if !safe {
				return false, nil
			}
		}
	}
	return true, nil
}
