package dagql

import (
	"context"
	"encoding/json"
	"fmt"
	"sync"
	"testing"

	"github.com/dagger/dagger/dagql/call"
	"github.com/dagger/dagger/util/hashutil"
	"github.com/opencontainers/go-digest"
	"github.com/stretchr/testify/require"
	"github.com/vektah/gqlparser/v2/ast"
	"github.com/zeebo/xxh3"
)

type lazyDigestQuery struct{}

func (lazyDigestQuery) Type() *ast.Type {
	return &ast.Type{NamedType: "Query", NonNull: true}
}

func eagerDigestForTest(t *testing.T, schema *ast.Schema) digest.Digest {
	t.Helper()
	h := xxh3.New()
	require.NoError(t, json.NewEncoder(h).Encode(schema))
	return digest.NewDigest(hashutil.XXH3, h)
}

func TestSchemaDigestIsLazyAndByteCompatible(t *testing.T) {
	srv, err := NewServer(t.Context(), lazyDigestQuery{})
	require.NoError(t, err)
	srv.InstallDirective(DirectiveSpec{Name: "futureOnly", ViewFilter: ExactView("future")})
	for _, view := range []call.View{"", "old", "future"} {
		srv.SchemaForView(view)
	}
	require.Empty(t, srv.schemaDigests, "building schemas for query validation must not hash them")
	require.NotEqual(t, eagerDigestForTest(t, srv.SchemaForView("old")), eagerDigestForTest(t, srv.SchemaForView("future")))
	for index, view := range []call.View{"", "old", "future"} {
		srv.View = view
		schema := srv.SchemaForView(view)
		want := eagerDigestForTest(t, schema)
		require.Equal(t, want, srv.SchemaDigest())
		require.Len(t, srv.schemaDigests, index+1, "only the requested view is hashed")
		require.Equal(t, want, srv.SchemaDigest())
		require.Same(t, schema, srv.SchemaForView(view))
	}
}

func TestSchemaDigestInvalidationBeforeAndAfterHash(t *testing.T) {
	srv, err := NewServer(t.Context(), lazyDigestQuery{})
	require.NoError(t, err)
	original := srv.Schema()
	originalDigest := eagerDigestForTest(t, original)
	srv.InstallDirective(DirectiveSpec{Name: "beforeDigest", Description: "first extension"})
	require.Empty(t, srv.schemas)
	require.Empty(t, srv.schemaDigests)
	first := srv.SchemaDigest()
	require.NotEqual(t, originalDigest, first)
	require.Equal(t, eagerDigestForTest(t, srv.Schema()), first)
	srv.InstallDirective(DirectiveSpec{Name: "afterDigest", Description: "second extension"})
	require.Empty(t, srv.schemas)
	require.Empty(t, srv.schemaDigests)
	second := srv.SchemaDigest()
	require.NotEqual(t, first, second)
	require.Equal(t, eagerDigestForTest(t, srv.Schema()), second)
	require.Equal(t, originalDigest, eagerDigestForTest(t, original), "old schema snapshots remain unchanged")
}

func TestSchemaDigestForkIsolation(t *testing.T) {
	srv, err := NewServer(t.Context(), lazyDigestQuery{})
	require.NoError(t, err)
	parent := srv.SchemaDigest()
	fork, err := srv.Fork(t.Context(), lazyDigestQuery{})
	require.NoError(t, err)
	fork.Schema()
	require.Empty(t, fork.schemaDigests)
	require.Equal(t, parent, fork.SchemaDigest())
	fork.InstallDirective(DirectiveSpec{Name: "forkOnly"})
	require.NotEqual(t, parent, fork.SchemaDigest())
	require.Equal(t, parent, srv.SchemaDigest())
	require.Nil(t, srv.Schema().Directives["forkOnly"])
	srv.InstallDirective(DirectiveSpec{Name: "parentOnly"})
	require.NotEqual(t, parent, srv.SchemaDigest())
	require.Nil(t, fork.Schema().Directives["parentOnly"])
}

func extendLazyDigestField(srv *Server, name string) {
	srv.Root().ObjectType().Extend(FieldSpec{Name: name, Type: String("")},
		func(ctx context.Context, _ AnyResult, _ map[string]Input) (AnyResult, error) {
			return NewResultForCurrentCall(ctx, String("value"))
		})
}

func TestSchemaDigestClassExtension(t *testing.T) {
	srv, err := NewServer(t.Context(), lazyDigestQuery{})
	require.NoError(t, err)
	original := srv.Schema()
	before := eagerDigestForTest(t, original)
	extendLazyDigestField(srv, "beforeHash")
	first := srv.SchemaDigest()
	require.NotEqual(t, before, first)
	require.Equal(t, eagerDigestForTest(t, srv.Schema()), first)
	extendLazyDigestField(srv, "afterHash")
	require.Empty(t, srv.schemaDigests)
	second := srv.SchemaDigest()
	require.NotEqual(t, first, second)
	require.Equal(t, eagerDigestForTest(t, srv.Schema()), second)
	require.Equal(t, before, eagerDigestForTest(t, original))
}

func TestSchemaDigestConcurrentReadsAndInvalidation(t *testing.T) {
	srv, err := NewServer(t.Context(), lazyDigestQuery{})
	require.NoError(t, err)
	var workers sync.WaitGroup
	start := make(chan struct{})
	empty := make(chan struct{}, 8)
	for range 8 {
		workers.Go(func() {
			<-start
			for range 40 {
				if srv.SchemaDigest() == "" {
					empty <- struct{}{}
					return
				}
			}
		})
	}
	workers.Go(func() {
		<-start
		for i := range 40 {
			if i%2 == 0 {
				srv.InstallDirective(DirectiveSpec{Name: fmt.Sprintf("extension%d", i)})
			} else {
				extendLazyDigestField(srv, fmt.Sprintf("field%d", i))
			}
		}
	})
	close(start)
	workers.Wait()
	close(empty)
	require.Empty(t, empty)
	require.Equal(t, eagerDigestForTest(t, srv.Schema()), srv.SchemaDigest())
}
