package dangv2

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"strconv"
	"sync"
	"sync/atomic"

	"github.com/Khan/genqlient/graphql"
	"github.com/dagger/dagger/dagql/call"
	lru "github.com/hashicorp/golang-lru/v2"
	"github.com/vito/dang/v2/pkg/dang"
	"github.com/vito/dang/v2/pkg/introspection"
)

// This is an opt-in experiment, not a cache of function results or parents.
var reusableDeclarationsEnabled atomic.Bool
var declarationHits, declarationMisses, declarationFallbacks atomic.Uint64
var knownInputIDsEnabled atomic.Bool
var knownInputIDsUsed atomic.Uint64

type invocationClientKey struct{}

// invocationClient is deliberately stateless: prepared code must not retain a
// session, cancellation context, engine client or workspace from its creator.
type invocationClient struct{}

func (client invocationClient) BindContext(ctx context.Context) graphql.Client {
	if current, ok := ctx.Value(invocationClientKey{}).(graphql.Client); ok {
		return current
	}
	return client
}

func (invocationClient) MakeRequest(ctx context.Context, req *graphql.Request, resp *graphql.Response) error {
	client, ok := ctx.Value(invocationClientKey{}).(graphql.Client)
	if !ok {
		return fmt.Errorf("Dang invocation has no GraphQL client")
	}
	return client.MakeRequest(ctx, req, resp)
}

type declarationKey struct {
	source, schema, directory string
}

func newDeclarationKey(source, schema *call.ID, directory string) (declarationKey, error) {
	if source == nil || schema == nil {
		return declarationKey{}, fmt.Errorf("declaration reuse requires source and schema IDs")
	}
	sourceID, err := source.Encode()
	if err != nil {
		return declarationKey{}, err
	}
	schemaID, err := schema.Encode()
	if err != nil {
		return declarationKey{}, err
	}
	return declarationKey{source: sourceID, schema: schemaID, directory: directory}, nil
}

// preparedDeclarations owns the schema already retained by its imported AST.
// It contains no invocation context or engine resource.
type preparedDeclarations struct {
	env    dang.ValueScope
	schema *introspection.Schema
}

type declarationRunner func(context.Context, string) (*preparedDeclarations, error)

type declarationEntry struct {
	mu                sync.Mutex
	prepared          *preparedDeclarations
	checked, reusable bool
}

var declarationEnvironments, _ = lru.New[declarationKey, *declarationEntry](32)

func reuseDangDeclarations(ctx context.Context, key declarationKey, run declarationRunner) (*preparedDeclarations, error) {
	entry := &declarationEntry{}
	previous, exists, _ := declarationEnvironments.PeekOrAdd(key, entry)
	if !exists {
		declarationMisses.Add(1)
	} else {
		entry = previous
	}
	entry.mu.Lock()
	if err := ctx.Err(); err != nil {
		entry.mu.Unlock()
		return nil, err
	}
	if entry.prepared != nil {
		prepared := entry.prepared
		entry.mu.Unlock()
		declarationHits.Add(1)
		return prepared, nil
	}
	if !entry.checked {
		var err error
		entry.reusable, err = dang.ReusableDirectoryDeclarations(ctx, key.directory)
		if err != nil {
			entry.mu.Unlock()
			return nil, err
		}
		entry.checked = true
	}
	if !entry.reusable {
		entry.mu.Unlock()
		declarationFallbacks.Add(1)
		return run(ctx, key.directory)
	}
	prepared, err := run(ctx, key.directory)
	if err == nil {
		err = ctx.Err()
	}
	if err == nil {
		entry.prepared = prepared
	}
	entry.mu.Unlock()
	return prepared, err
}

func ReusableDeclarationsDiagnostic(w http.ResponseWriter, r *http.Request) {
	if r.Method == http.MethodPost {
		enabled, err := strconv.ParseBool(r.URL.Query().Get("enabled"))
		if err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}
		reusableDeclarationsEnabled.Store(enabled)
	} else if r.Method != http.MethodGet {
		http.Error(w, "GET or POST required", http.StatusMethodNotAllowed)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(map[string]any{
		"enabled": reusableDeclarationsEnabled.Load(),
		"entries": declarationEnvironments.Len(),
		"hits":    declarationHits.Load(), "misses": declarationMisses.Load(),
		"fallbacks": declarationFallbacks.Load(),
	})
}

func KnownInputIDsDiagnostic(w http.ResponseWriter, r *http.Request) {
	if r.Method == http.MethodPost {
		enabled, err := strconv.ParseBool(r.URL.Query().Get("enabled"))
		if err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}
		knownInputIDsEnabled.Store(enabled)
	} else if r.Method != http.MethodGet {
		http.Error(w, "GET or POST required", http.StatusMethodNotAllowed)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(map[string]any{"enabled": knownInputIDsEnabled.Load(), "converted": knownInputIDsUsed.Load()})
}
