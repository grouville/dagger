package filesync

import (
	"context"
	"encoding/json"

	"github.com/dagger/dagger/engine/wcprof"
	"github.com/dagger/dagger/internal/buildkit/util/bklog"
	"github.com/dagger/dagger/util/layercopy"
)

// syncPhaseProfile records real sequential intervals, never synthesized sums of
// overlapping work. It is diagnostic instrumentation shared by both benchmark
// arms; granular work counters are kept separate from this critical-path view.
type syncPhaseProfile struct {
	parent context.Context
	op     *wcprof.Op
}

func (p *syncPhaseProfile) next(ctx context.Context, class string) context.Context {
	p.end(nil)
	if !wcprof.Enabled(ctx) {
		return ctx
	}
	// Keep OTel and other context values while making phases siblings.
	ctx = wcprof.ContextWithOpID(ctx, wcprof.CurrentOpID(p.parent))
	ctx, op := wcprof.BeginOp(ctx, wcprof.OpKindIO, "filesync.phase."+class, wcprof.OpOpts{})
	p.op = op
	return ctx
}

func (p *syncPhaseProfile) end(err error) {
	if p.op != nil {
		p.op.EndErr(err)
		p.op = nil
	}
}

func newCopyProfile(ctx context.Context) *layercopy.CopyProfile {
	if !wcprof.Enabled(ctx) {
		return nil
	}
	return &layercopy.CopyProfile{}
}

func logCopyProfile(ctx context.Context, profile *layercopy.CopyProfile) {
	if profile == nil {
		return
	}
	data, err := json.Marshal(profile)
	if err == nil {
		bklog.G(ctx).Debugf("filesync.copy.profile %s", data)
	}
}
