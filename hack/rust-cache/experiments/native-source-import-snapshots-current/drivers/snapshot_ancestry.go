package main

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"strings"

	"github.com/containerd/containerd/v2/core/snapshots"
	"github.com/containerd/containerd/v2/core/snapshots/storage"
)

type snapshot struct {
	Parent    string `json:"parent"`
	StorageID string `json:"storage_id"`
	Size      int64  `json:"size"`
}

func short(name string) string {
	return name[strings.LastIndex(name, "/")+1:]
}

func main() {
	if len(os.Args) != 2 {
		panic("supply an offline copy of snapshot metadata")
	}
	store, err := storage.NewMetaStore(os.Args[1])
	if err != nil {
		panic(err)
	}
	defer store.Close()
	ctx, tx, err := store.TransactionContext(context.Background(), false)
	if err != nil {
		panic(err)
	}
	defer tx.Rollback()
	values := map[string]snapshot{}
	err = storage.WalkInfo(ctx, func(ctx context.Context, info snapshots.Info) error {
		storageID, _, usage, err := storage.GetInfo(ctx, info.Name)
		if err != nil {
			return err
		}
		id := short(info.Name)
		if _, ok := values[id]; ok {
			return fmt.Errorf("duplicate snapshot suffix %q", id)
		}
		values[id] = snapshot{Parent: short(info.Parent), StorageID: storageID, Size: usage.Size}
		return nil
	})
	if err != nil {
		panic(err)
	}
	if err := json.NewEncoder(os.Stdout).Encode(values); err != nil {
		panic(err)
	}
}
