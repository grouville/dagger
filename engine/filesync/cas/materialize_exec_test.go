package cas

import (
	"errors"
	"fmt"
	"testing"

	"gotest.tools/v3/assert"
	is "gotest.tools/v3/assert/cmp"
)

func TestMaterializeExecAppliesOperations(t *testing.T) {
	t.Parallel()

	applier := &fakeMaterializeApplier{}
	plan := MaterializePlan{
		Deletes: []string{"dir/sub/file.txt"},
		Upserts: []MaterializeUpsert{
			{
				Path:  "dir/new.txt",
				Entry: Entry{Path: "dir/new.txt", Kind: EntryFile},
			},
		},
	}

	err := ExecuteMaterializePlan(applier, plan)
	assert.NilError(t, err)
	assert.DeepEqual(t, applier.ops, []string{
		"delete:dir/sub/file.txt",
		"upsert:dir/new.txt",
		"close",
	})
}

func TestMaterializeExecClosesOnFailure(t *testing.T) {
	t.Parallel()

	applier := &fakeMaterializeApplier{
		failDeletePath: "dir/sub/file.txt",
	}
	plan := MaterializePlan{
		Deletes: []string{"dir/sub/file.txt"},
		Upserts: []MaterializeUpsert{
			{Path: "dir/new.txt", Entry: Entry{Path: "dir/new.txt", Kind: EntryFile}},
		},
	}

	err := ExecuteMaterializePlan(applier, plan)
	assert.Assert(t, is.ErrorContains(err, "delete \"dir/sub/file.txt\""))
	assert.DeepEqual(t, applier.ops, []string{
		"delete:dir/sub/file.txt",
		"close",
	})
}

func TestMaterializeExecCloseErrorIsReturned(t *testing.T) {
	t.Parallel()

	applier := &fakeMaterializeApplier{
		closeErr: errors.New("close failure"),
	}
	plan := MaterializePlan{}

	err := ExecuteMaterializePlan(applier, plan)
	assert.Assert(t, is.ErrorContains(err, "close applier"))
	assert.DeepEqual(t, applier.ops, []string{"close"})
}

type fakeMaterializeApplier struct {
	ops            []string
	failDeletePath string
	failUpsertPath string
	closeErr       error
}

func (a *fakeMaterializeApplier) Delete(path string) error {
	a.ops = append(a.ops, "delete:"+path)
	if path == a.failDeletePath {
		return fmt.Errorf("forced delete error")
	}
	return nil
}

func (a *fakeMaterializeApplier) Upsert(path string, _ Entry) error {
	a.ops = append(a.ops, "upsert:"+path)
	if path == a.failUpsertPath {
		return fmt.Errorf("forced upsert error")
	}
	return nil
}

func (a *fakeMaterializeApplier) Close() error {
	a.ops = append(a.ops, "close")
	return a.closeErr
}
