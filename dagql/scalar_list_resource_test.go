package dagql

import (
	"context"
	"sync/atomic"
	"testing"

	"github.com/stretchr/testify/require"
	"github.com/vektah/gqlparser/v2/ast"
)

type projectionResourceRecord struct {
	Name     string `field:"true"`
	released *atomic.Int64
}

func (*projectionResourceRecord) Type() *ast.Type {
	return &ast.Type{NamedType: "ProjectionResourceRecord", NonNull: true}
}

func (r *projectionResourceRecord) OnRelease(context.Context) error {
	r.released.Add(1)
	return nil
}

func TestScalarListProjectionReleasesResourceItems(t *testing.T) {
	ctx, srv, _ := scalarProjectionFixture(t, 1)
	var released atomic.Int64
	Fields[*projectionResourceRecord]{}.Install(srv)
	Fields[*projectionTestQuery]{Func("resourceRecords", func(context.Context, *projectionTestQuery, struct{}) ([]*projectionResourceRecord, error) {
		return []*projectionResourceRecord{{Name: "owned", released: &released}}, nil
	})}.Install(srv)
	_, err := srv.Query(ctx, `{resourceRecords{name}}`, nil)
	require.NoError(t, err)
	cache, err := EngineCache(ctx)
	require.NoError(t, err)
	require.NoError(t, cache.ReleaseSession(ctx, "scalar-projection"))
	_, err = cache.Prune(ctx, []CachePrunePolicy{{All: true}})
	require.NoError(t, err)
	require.Equal(t, int64(2), released.Load(), "reading metadata must retain the item's release lifecycle")
}
