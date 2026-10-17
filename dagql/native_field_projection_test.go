package dagql

import (
	"context"
	"fmt"
	"testing"

	"github.com/stretchr/testify/require"
	"github.com/vektah/gqlparser/v2/ast"
)

type projectionNativeHolder struct {
	Entries []*projectionTestRecord `field:"true"`
}

func (*projectionNativeHolder) Type() *ast.Type {
	return &ast.Type{NamedType: "ProjectionNativeHolder", NonNull: true}
}

func TestScalarListProjectionNativeFieldAvoidsItemRows(t *testing.T) {
	ctx, srv, _ := scalarProjectionFixture(t, 3)
	Fields[*projectionNativeHolder]{}.Install(srv)
	Fields[*projectionTestQuery]{Func("nativeHolder", func(context.Context, *projectionTestQuery, struct{}) (*projectionNativeHolder, error) {
		return &projectionNativeHolder{Entries: []*projectionTestRecord{{Name: "a"}, {Name: "b"}, {Name: "c"}}}, nil
	})}.Install(srv)
	var holder ObjectResult[*projectionNativeHolder]
	require.NoError(t, srv.Select(ctx, srv.Root(), &holder, Selector{Field: "nativeHolder"}))
	list, err := holder.Select(ctx, srv, Selector{Field: "entries"})
	require.NoError(t, err)
	require.IsType(t, DynamicArrayOutput{}, list.Unwrap())
	require.True(t, srv.canProjectScalarList(list, []Selection{{Selector: Selector{Field: "name"}}}),
		"native struct fields must be eligible, not silently fall back")

	cache, err := EngineCache(ctx)
	require.NoError(t, err)
	itemRows := func() int {
		cache.egraphMu.Lock()
		defer cache.egraphMu.Unlock()
		count := 0
		for _, row := range cache.resultsByID {
			call := row.loadResultCall()
			if call != nil && call.Nth != 0 && call.Receiver != nil && call.Receiver.ResultID == uint64(list.cacheSharedResult().id) {
				count++
			}
		}
		return count
	}
	require.Zero(t, itemRows())
	got, err := srv.Query(ctx, `{nativeHolder{entries{name}}}`, nil)
	require.NoError(t, err)
	require.Equal(t, map[string]any{"nativeHolder": map[string]any{"entries": []any{
		map[string]any{"name": String("a")}, map[string]any{"name": String("b")}, map[string]any{"name": String("c")},
	}}}, got)
	require.Zero(t, itemRows(), "scalar output must not attach an object per list item")

	var rows ObjectResultArray[*projectionTestRecord]
	require.NoError(t, srv.Select(ctx, srv.Root(), &rows, Selector{Field: "nativeHolder"}, Selector{Field: "entries"}))
	require.Len(t, rows, 3)
	for i, row := range rows {
		id, err := row.ID()
		require.NoError(t, err)
		loaded, err := srv.Load(ctx, id)
		require.NoError(t, err)
		var name String
		require.NoError(t, srv.Select(ctx, loaded, &name, Selector{Field: "name"}))
		require.Equal(t, String(fmt.Sprintf("%c", 'a'+i)), name)
	}
	require.Equal(t, 3, itemRows(), "explicit object access still needs attached identities")
}
