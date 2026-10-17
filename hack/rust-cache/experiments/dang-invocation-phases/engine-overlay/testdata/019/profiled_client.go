package dangshared

import (
	"context"

	"github.com/Khan/genqlient/graphql"
	"github.com/dagger/dagger/engine/wcprof"
)

// Installed only for a recorded invocation. Keep the real HTTP client, request,
// response and errors; measure the caller's complete API wait in its context.
type profiledNestedClient struct {
	graphql.Client
}

func (client profiledNestedClient) MakeRequest(ctx context.Context, req *graphql.Request, resp *graphql.Response) error {
	ctx, op := wcprof.BeginOp(ctx, wcprof.OpKindInternal, "dang.apiRequest", wcprof.OpOpts{})
	err := client.Client.MakeRequest(ctx, req, resp)
	op.EndErr(err)
	return err
}
