package dagql_test

import (
	"context"
	"encoding/json"
	"fmt"
	"sync"
	"testing"

	"github.com/opencontainers/go-digest"
	"github.com/stretchr/testify/require"
	"github.com/zeebo/xxh3"

	"github.com/dagger/dagger/dagql"
	"github.com/dagger/dagger/dagql/call"
	"github.com/dagger/dagger/util/hashutil"
)

func TestSchemaDigestMatchesEncodedSchema(t *testing.T) {
	srv := newExternalDagqlServerForTest(t, Query{})
	InstallViewer(srv)
	for _, view := range []call.View{"firstView", "secondView", "firstView"} {
		srv.View = view
		h := xxh3.New()
		require.NoError(t, json.NewEncoder(h).Encode(srv.Schema()))
		want := digest.NewDigest(hashutil.XXH3, h)
		var wg sync.WaitGroup
		var results [8]digest.Digest
		for i := range results {
			wg.Go(func() { results[i] = srv.SchemaDigest() })
		}
		wg.Wait()
		for _, got := range results {
			require.Equal(t, want, got)
		}
	}
	before := srv.SchemaDigest()
	srv.Root().ObjectType().Extend(dagql.FieldSpec{Name: "added", Type: dagql.String("")}, nil)
	h := xxh3.New()
	require.NoError(t, json.NewEncoder(h).Encode(srv.Schema()))
	require.Equal(t, digest.NewDigest(hashutil.XXH3, h), srv.SchemaDigest())
	require.NotEqual(t, before, srv.SchemaDigest())
}

func BenchmarkForkSchema(b *testing.B) {
	srv := newExternalDagqlServerForTest(b, Query{})
	for i := range 1024 {
		srv.Root().ObjectType().Extend(dagql.FieldSpec{Name: fmt.Sprintf("field%d", i), Type: dagql.String("")}, nil)
	}
	b.ReportAllocs()
	b.ResetTimer()
	for b.Loop() {
		fork, err := srv.Fork(context.Background(), Query{})
		if err != nil {
			b.Fatal(err)
		}
		fork.Schema()
	}
}
