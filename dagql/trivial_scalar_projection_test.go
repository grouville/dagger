package dagql

import (
	"context"
	"fmt"
	"sync"
	"sync/atomic"
	"testing"

	"github.com/dagger/dagger/engine"
	"github.com/stretchr/testify/require"
	"github.com/vektah/gqlparser/v2/ast"
)

type projectionTestQuery struct{}

func (*projectionTestQuery) Type() *ast.Type { return &ast.Type{NamedType: "Query", NonNull: true} }

type projectionTestRecord struct {
	Name    string               `field:"true"`
	Count   int                  `field:"true"`
	Ratio   float64              `field:"true"`
	Enabled bool                 `field:"true"`
	Note    *string              `field:"true"`
	Names   []string             `field:"true"`
	Child   *projectionTestChild `field:"true"`
}

func (*projectionTestRecord) Type() *ast.Type {
	return &ast.Type{NamedType: "ProjectionTestRecord", NonNull: true}
}

type projectionTestChild struct {
	Name string `field:"true"`
}

type projectionTestOwnedScalar struct {
	Value cacheTestOnReleaseInt `field:"true"`
}

func (*projectionTestOwnedScalar) Type() *ast.Type {
	return &ast.Type{NamedType: "ProjectionTestOwnedScalar", NonNull: true}
}

func TestTrivialScalarProjectionKeepsOwnedScalarAttached(t *testing.T) {
	ctx, srv, _ := scalarProjectionFixture(t, 1)
	Fields[*projectionTestOwnedScalar]{}.Install(srv)
	Fields[*projectionTestQuery]{Func("owned", func(context.Context, *projectionTestQuery, struct{}) (*projectionTestOwnedScalar, error) {
		return &projectionTestOwnedScalar{Value: cacheTestOnReleaseInt{Int: Int(7), onRelease: func(context.Context) error { return nil }}}, nil
	})}.Install(srv)
	var owner ObjectResult[*projectionTestOwnedScalar]
	require.NoError(t, srv.Select(ctx, srv.Root(), &owner, Selector{Field: "owned"}))
	value, err := owner.Select(ctx, srv, Selector{Field: "value"})
	require.NoError(t, err)
	require.Equal(t, Int(7), value.Unwrap().(cacheTestOnReleaseInt).Int)
	_, err = value.ID()
	require.NoError(t, err, "a scalar owning a release callback still needs an attached result")
}

func (*projectionTestChild) Type() *ast.Type {
	return &ast.Type{NamedType: "ProjectionTestChild", NonNull: true}
}

func scalarProjectionFixture(t testing.TB, count int) (context.Context, *Server, *atomic.Int64) {
	t.Helper()
	ctx := engine.ContextWithClientMetadata(t.Context(), &engine.ClientMetadata{ClientID: "scalar-projection", SessionID: "scalar-projection"})
	cache, err := NewCache(ctx, "", nil, nil)
	require.NoError(t, err)
	t.Cleanup(func() { require.NoError(t, cache.CloseDiscardingPersistence()) })
	ctx = ContextWithCache(ctx, cache)
	srv, err := NewServer(ctx, &projectionTestQuery{})
	require.NoError(t, err)
	Fields[*projectionTestChild]{}.Install(srv)
	srv.InstallObject(NewClass(srv, ClassOpts[*projectionTestRecord]{PureData: true}))
	computed := new(atomic.Int64)
	Fields[*projectionTestRecord]{Func("computed", func(_ context.Context, r *projectionTestRecord, _ struct{}) (int, error) {
		computed.Add(1)
		return r.Count + 1, nil
	})}.Install(srv)
	Fields[*projectionTestQuery]{Func("records", func(_ context.Context, _ *projectionTestQuery, args struct{ Generation int }) ([]*projectionTestRecord, error) {
		rows := make([]*projectionTestRecord, count)
		for i := range rows {
			name := fmt.Sprintf("record-%d-%d", args.Generation, i)
			var note *string
			if args.Generation%2 != 0 {
				note = &name
			}
			rows[i] = &projectionTestRecord{Name: name, Count: args.Generation, Ratio: float64(args.Generation) / 2,
				Enabled: args.Generation%2 != 0, Note: note, Names: []string{name}, Child: &projectionTestChild{Name: name}}
		}
		return rows, nil
	})}.Install(srv)
	return ctx, srv, computed
}

// Object and array fields must keep their runtime identities when scalar data
// fields stop publishing their own rows. Reading a retained ID must still use
// that parent's data after a newer generation has been read.
func TestTrivialScalarProjectionKeepsObjectAndArrayIdentity(t *testing.T) {
	ctx, srv, computed := scalarProjectionFixture(t, 1)
	var retained ObjectResult[*projectionTestRecord]
	for generation := range 2 {
		var rows ObjectResultArray[*projectionTestRecord]
		require.NoError(t, srv.Select(ctx, srv.Root(), &rows, Selector{Field: "records", Args: []NamedInput{{Name: "generation", Value: Int(generation)}}}))
		require.Len(t, rows, 1)
		row := rows[0]
		id, err := row.ID()
		require.NoError(t, err)
		loaded, err := srv.Load(ctx, id)
		require.NoError(t, err)
		for _, field := range []string{"name", "count", "ratio", "enabled", "note", "names", "child", "computed"} {
			value, err := loaded.Select(ctx, srv, Selector{Field: field})
			require.NoError(t, err)
			if field == "names" || field == "child" {
				_, err := value.ID()
				require.NoError(t, err, "identity of %s", field)
			}
		}
		var value Int
		require.NoError(t, srv.Select(ctx, loaded, &value, Selector{Field: "computed"}))
		require.Equal(t, Int(generation+1), value)
		require.Equal(t, int64(generation+1), computed.Load(), "ordinary functions must remain cached")
		if generation == 0 {
			retained = row
		}
	}
	var name String
	require.NoError(t, srv.Select(ctx, retained, &name, Selector{Field: "name"}))
	require.Equal(t, String("record-0-0"), name)
	checks := make(chan error, 8)
	var wg sync.WaitGroup
	for range 8 {
		wg.Go(func() {
			var count Int
			err := srv.Select(ctx, retained, &count, Selector{Field: "count"})
			if err == nil && count != 0 {
				err = fmt.Errorf("retained count: got %d, want 0", count)
			}
			checks <- err
		})
	}
	wg.Wait()
	close(checks)
	for err := range checks {
		require.NoError(t, err)
	}
	for generation := range 2 {
		result, err := srv.Query(ctx, `query($g:Int!){records(generation:$g){name count ratio enabled note child{id name}}}`, map[string]any{"g": generation})
		require.NoError(t, err)
		row := result["records"].([]any)[0].(map[string]any)
		require.Equal(t, String(fmt.Sprintf("record-%d-0", generation)), row["name"])
		require.Equal(t, Int(generation), row["count"])
		require.Equal(t, Float(float64(generation)/2), row["ratio"])
		require.Equal(t, Boolean(generation != 0), row["enabled"])
		if generation == 0 {
			require.Nil(t, row["note"])
		} else {
			require.Equal(t, String("record-1-0"), row["note"])
		}
	}
}
