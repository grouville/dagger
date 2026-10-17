package core

import (
	"context"
	"sync"

	"github.com/dagger/dagger/dagql"
)

// A nonzero-sized token preserves a node's identity through Artifact.Clone.
type collectionEvaluationKey byte

type collectionEvaluationContextKey struct{}

type collectionEvaluation struct {
	values sync.Map // *collectionEvaluationKey -> dagql.AnyObjectResult
}

func collectionEvaluationFromContext(ctx context.Context) *collectionEvaluation {
	evaluation, _ := ctx.Value(collectionEvaluationContextKey{}).(*collectionEvaluation)
	return evaluation
}

func evaluatedCollection(ctx context.Context, key *collectionEvaluationKey) dagql.AnyObjectResult {
	if key == nil {
		return nil
	}
	evaluation := collectionEvaluationFromContext(ctx)
	if evaluation == nil {
		return nil
	}
	value, ok := evaluation.values.Load(key)
	if !ok {
		return nil
	}
	return value.(dagql.AnyObjectResult)
}
