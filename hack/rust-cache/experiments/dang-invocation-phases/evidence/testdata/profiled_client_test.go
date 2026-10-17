package dangshared

import (
	"bytes"
	"context"
	"errors"
	"testing"

	"github.com/Khan/genqlient/graphql"
	"github.com/dagger/dagger/engine/wcprof"
	"github.com/stretchr/testify/require"
)

type phaseProfileTestClient struct {
	makeRequest func(context.Context, *graphql.Request, *graphql.Response) error
}

func (client phaseProfileTestClient) MakeRequest(ctx context.Context, req *graphql.Request, resp *graphql.Response) error {
	return client.makeRequest(ctx, req, resp)
}

func TestProfiledNestedClientPreservesCallAndParent(t *testing.T) {
	wcprof.EnsureRecorder()
	for _, canceled := range []bool{false, true} {
		t.Run(map[bool]string{false: "error", true: "cancellation"}[canceled], func(t *testing.T) {
			type key struct{}
			ctx := context.WithValue(wcprof.ContextWithProfiling(t.Context()), key{}, "caller scope")
			ctx, parent := wcprof.BeginOp(ctx, wcprof.OpKindInternal, "dang.evaluateFunction", wcprof.OpOpts{})
			require.NotNil(t, parent)
			ctx, cancel := context.WithCancel(ctx)
			defer cancel()
			cause := errors.New("API error")
			if canceled {
				cancel()
				cause = context.Canceled
			}
			req := &graphql.Request{Query: "query { value }", Variables: map[string]any{"key": "value"}}
			resp := &graphql.Response{Data: map[string]any{}}
			var requestOp uint64
			called := false
			client := profiledNestedClient{Client: phaseProfileTestClient{makeRequest: func(got context.Context, request *graphql.Request, response *graphql.Response) error {
				called = true
				require.Same(t, req, request)
				require.Same(t, resp, response)
				require.Equal(t, "caller scope", got.Value(key{}))
				require.Equal(t, ctx.Err(), got.Err())
				requestOp = wcprof.CurrentOpID(got)
				require.NotZero(t, requestOp)
				require.NotEqual(t, parent.ID(), requestOp)
				response.Data.(map[string]any)["value"] = "returned value"
				return cause
			}}}
			err := client.MakeRequest(ctx, req, resp)
			parent.EndErr(err)
			require.True(t, called)
			require.ErrorIs(t, err, cause)
			require.Equal(t, "returned value", resp.Data.(map[string]any)["value"])
			var dump bytes.Buffer
			require.NoError(t, wcprof.Active().WriteDump(&dump, false))
			header, events, err := wcprof.ReadDump(&dump)
			require.NoError(t, err)
			found := false
			for _, event := range events {
				if event.Type == "op" && event.OpID == requestOp {
					found = true
					require.Equal(t, "dang.apiRequest", header.Strings[event.ClassID])
					require.Equal(t, parent.ID(), event.ParentID)
					require.Equal(t, "error", event.Outcome)
				}
			}
			require.True(t, found, "API wait was not recorded under the evaluator")
		})
	}
}
