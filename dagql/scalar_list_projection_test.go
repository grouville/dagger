package dagql

import (
	"context"
	"encoding/json"
	"fmt"
	"sync"
	"sync/atomic"
	"testing"

	"github.com/dagger/dagger/engine"
	"github.com/stretchr/testify/require"
)

func TestScalarListProjectionPreservesDataAndLaterIDs(t *testing.T) {
	ctx, srv, _ := scalarProjectionFixture(t, 3)
	for generation := range 2 {
		result, err := srv.Query(ctx, `query($g:Int!){records(generation:$g){renamed:name count ratio enabled note}}`, map[string]any{"g": generation})
		require.NoError(t, err)
		encoded, err := json.Marshal(result)
		require.NoError(t, err)
		var decoded struct {
			Records []struct {
				Renamed string
				Count   int
				Ratio   float64
				Enabled bool
				Note    *string
			}
		}
		require.NoError(t, json.Unmarshal(encoded, &decoded))
		require.Len(t, decoded.Records, 3)
		for i, row := range decoded.Records {
			require.Equal(t, fmt.Sprintf("record-%d-%d", generation, i), row.Renamed)
			require.Equal(t, generation, row.Count)
			require.Equal(t, float64(generation)/2, row.Ratio)
			require.Equal(t, generation != 0, row.Enabled)
			if generation == 0 {
				require.Nil(t, row.Note)
			} else {
				require.Equal(t, row.Renamed, *row.Note)
			}
		}
	}
	var retained ObjectResultArray[*projectionTestRecord]
	require.NoError(t, srv.Select(ctx, srv.Root(), &retained, Selector{Field: "records", Args: []NamedInput{{Name: "generation", Value: Int(0)}}}))
	for i, row := range retained {
		id, err := row.ID()
		require.NoError(t, err)
		loaded, err := srv.Load(ctx, id)
		require.NoError(t, err)
		var name String
		require.NoError(t, srv.Select(ctx, loaded, &name, Selector{Field: "name"}))
		require.Equal(t, String(fmt.Sprintf("record-0-%d", i)), name)
	}
}

func TestScalarListProjectionKeepsGetterTelemetry(t *testing.T) {
	ctx, srv, _ := scalarProjectionFixture(t, 3)
	var dataCalls atomic.Int64
	srv.telemetry = func(ctx context.Context, req *CallRequest) (context.Context, func(AnyResult, bool, *error)) {
		switch req.Field {
		case "name", "count", "ratio", "enabled", "note":
			dataCalls.Add(1)
		}
		return ctx, NoopDone
	}
	_, err := srv.Query(ctx, `{records(generation:0){name count ratio enabled note}}`, nil)
	require.NoError(t, err)
	require.Equal(t, int64(15), dataCalls.Load())
}

func TestScalarListProjectionKeepsComputedFieldsCached(t *testing.T) {
	ctx, srv, computed := scalarProjectionFixture(t, 3)
	for range 2 {
		_, err := srv.Query(ctx, `{records(generation:0){name computed child{id name}}}`, nil)
		require.NoError(t, err)
	}
	require.Equal(t, int64(3), computed.Load())
}

func TestScalarListProjectionKeepsCustomScalarsAttached(t *testing.T) {
	ctx, srv, _ := scalarProjectionFixture(t, 1)
	Fields[*projectionTestOwnedScalar]{}.Install(srv)
	Fields[*projectionTestQuery]{Func("ownedRecords", func(context.Context, *projectionTestQuery, struct{}) ([]*projectionTestOwnedScalar, error) {
		return []*projectionTestOwnedScalar{{Value: cacheTestOnReleaseInt{Int: Int(7), onRelease: func(context.Context) error { return nil }}}}, nil
	})}.Install(srv)
	_, err := srv.Query(ctx, `{ownedRecords{value}}`, nil)
	require.NoError(t, err)
	var rows ObjectResultArray[*projectionTestOwnedScalar]
	require.NoError(t, srv.Select(ctx, srv.Root(), &rows, Selector{Field: "ownedRecords"}))
	value, err := rows[0].Select(ctx, srv, Selector{Field: "value"})
	require.NoError(t, err)
	_, err = value.ID()
	require.NoError(t, err)
}

func TestScalarListProjectionDoesNotMixConcurrentLists(t *testing.T) {
	ctx, srv, _ := scalarProjectionFixture(t, 1)
	var calls atomic.Int64
	Fields[*projectionTestQuery]{Func("volatileRecords", func(context.Context, *projectionTestQuery, struct{}) ([]*projectionTestRecord, error) {
		n := calls.Add(1)
		return []*projectionTestRecord{{Name: fmt.Sprint(n), Count: int(n)}, {Name: fmt.Sprint(n), Count: int(n)}}, nil
	}).WithInput(PerCallInput)}.Install(srv)
	results := make([]map[string]any, 2)
	errs := make([]error, 2)
	var wg sync.WaitGroup
	for i := range results {
		wg.Go(func() {
			requestCtx := engine.ContextWithClientMetadata(ctx, &engine.ClientMetadata{
				ClientID:  fmt.Sprintf("projection-client-%d", i),
				SessionID: fmt.Sprintf("projection-session-%d", i),
			})
			results[i], errs[i] = srv.Query(requestCtx, `{volatileRecords{name count}}`, nil)
		})
	}
	wg.Wait()
	for _, err := range errs {
		require.NoError(t, err)
	}
	seen := map[int]bool{}
	for _, result := range results {
		encoded, err := json.Marshal(result)
		require.NoError(t, err)
		var decoded struct {
			VolatileRecords []struct {
				Name  string
				Count int
			}
		}
		require.NoError(t, json.Unmarshal(encoded, &decoded))
		require.Len(t, decoded.VolatileRecords, 2)
		n := decoded.VolatileRecords[0].Count
		seen[n] = true
		for _, row := range decoded.VolatileRecords {
			require.Equal(t, n, row.Count)
			require.Equal(t, fmt.Sprint(n), row.Name)
		}
	}
	require.Len(t, seen, 2)
}
