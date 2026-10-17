package dang

import (
	"crypto/sha256"
	"fmt"
	"os"
	"reflect"
	"strings"
	"sync"

	"github.com/hashicorp/golang-lru/v2/simplelru"
)

// A parse blueprint retains syntax before inference, never a module's schema,
// client or values. Each use constructs independent pointers and containers
// and supplies the current file path for source locations.
type parseBlueprint func(filename reflect.Value) reflect.Value

type parseBlueprintKey struct {
	digest [32]byte
}

type blueprintEntry struct {
	create parseBlueprint
	weight int64
}

type blueprintCache struct {
	mu      sync.Mutex
	entries *simplelru.LRU[parseBlueprintKey, blueprintEntry]
	weight  int64
	budget  int64
}

func newBlueprintCache(entries int, budget int64) *blueprintCache {
	cache := &blueprintCache{budget: budget}
	cache.entries, _ = simplelru.NewLRU[parseBlueprintKey, blueprintEntry](entries,
		func(_ parseBlueprintKey, entry blueprintEntry) { cache.weight -= entry.weight })
	return cache
}

func (cache *blueprintCache) Get(key parseBlueprintKey) (parseBlueprint, bool) {
	cache.mu.Lock()
	defer cache.mu.Unlock()
	entry, ok := cache.entries.Get(key)
	return entry.create, ok
}

func (cache *blueprintCache) Add(key parseBlueprintKey, create parseBlueprint, weight int64) {
	cache.mu.Lock()
	defer cache.mu.Unlock()
	// Concurrent misses may build the same entry; the first one is enough.
	if cache.entries.Contains(key) || weight > cache.budget {
		return
	}
	cache.weight += weight
	cache.entries.Add(key, blueprintEntry{create: create, weight: weight})
	for cache.weight > cache.budget {
		cache.entries.RemoveOldest()
	}
}

var parseBlueprints = newBlueprintCache(128, 64<<20)

func parseFileBlueprint(filename string) (any, error) {
	return parseFileBlueprintWithCache(filename, parseBlueprints)
}

func parseFileBlueprintWithCache(filename string, cache *blueprintCache) (any, error) {
	source, err := os.ReadFile(filename)
	if err != nil {
		return nil, err
	}
	key := parseBlueprintKey{digest: sha256.Sum256(source)}
	if blueprint, ok := cache.Get(key); ok {
		return blueprint(reflect.ValueOf(filename)).Interface().(*FileBlock), nil
	}
	parsed, err := ParseWithRecovery(filename, source, GlobalStore("filePath", filename))
	if err != nil {
		return nil, err
	}
	block, ok := parsed.(*FileBlock)
	if !ok {
		return nil, fmt.Errorf("parsed result for %s is not a FileBlock", filename)
	}
	weight := int64(128) // key and LRU entry
	blueprint, err := syntaxBlueprintWeighted(reflect.ValueOf(block), &weight, cache.budget)
	if err != nil {
		// New syntax fields must preserve parsing even before the blueprint
		// builder supports them. This result has not been inferred yet.
		return block, nil
	}
	cache.Add(key, blueprint, weight)
	return block, nil
}

func syntaxBlueprint(value reflect.Value) (parseBlueprint, error) {
	weight := int64(0)
	return syntaxBlueprintWeighted(value, &weight, 64<<20)
}

func syntaxBlueprintWeighted(value reflect.Value, weight *int64, budget int64) (parseBlueprint, error) {
	// Account for a closure, reflected scalar/type metadata and child storage.
	// This is a cache weight, not exact allocator heap accounting.
	*weight += 128
	if *weight > budget {
		return nil, fmt.Errorf("parse blueprint exceeds cache budget")
	}
	typeOf := value.Type()
	if value.IsZero() {
		return func(filename reflect.Value) reflect.Value { return reflect.Zero(typeOf) }, nil
	}
	switch value.Kind() {
	case reflect.Pointer:
		element, err := syntaxBlueprintWeighted(value.Elem(), weight, budget)
		if err != nil {
			return nil, err
		}
		return func(filename reflect.Value) reflect.Value {
			result := reflect.New(typeOf.Elem())
			result.Elem().Set(element(filename))
			return result
		}, nil
	case reflect.Interface:
		element, err := syntaxBlueprintWeighted(value.Elem(), weight, budget)
		if err != nil {
			return nil, err
		}
		return func(filename reflect.Value) reflect.Value {
			result := reflect.New(typeOf).Elem()
			result.Set(element(filename))
			return result
		}, nil
	case reflect.Struct:
		*weight += int64(value.NumField()) * 8
		if *weight > budget {
			return nil, fmt.Errorf("parse blueprint exceeds cache budget")
		}
		fields := make([]parseBlueprint, value.NumField())
		for i := range fields {
			field := typeOf.Field(i)
			if field.PkgPath != "" {
				if !value.Field(i).IsZero() {
					return nil, fmt.Errorf("nonzero private parse field %s.%s", typeOf, field.Name)
				}
				continue
			}
			if typeOf == reflect.TypeFor[SourceLocation]() && field.Name == "Filename" {
				// Source paths belong to this use of the syntax, not its content.
				fields[i] = func(filename reflect.Value) reflect.Value { return filename }
				continue
			}
			var err error
			fields[i], err = syntaxBlueprintWeighted(value.Field(i), weight, budget)
			if err != nil {
				return nil, err
			}
		}
		return func(filename reflect.Value) reflect.Value {
			result := reflect.New(typeOf).Elem()
			for i, field := range fields {
				if field != nil {
					result.Field(i).Set(field(filename))
				}
			}
			return result
		}, nil
	case reflect.Slice:
		*weight += int64(value.Len()) * 8
		if *weight > budget {
			return nil, fmt.Errorf("parse blueprint exceeds cache budget")
		}
		elements := make([]parseBlueprint, value.Len())
		for i := range elements {
			var err error
			elements[i], err = syntaxBlueprintWeighted(value.Index(i), weight, budget)
			if err != nil {
				return nil, err
			}
		}
		return func(filename reflect.Value) reflect.Value {
			result := reflect.MakeSlice(typeOf, len(elements), len(elements))
			for i, element := range elements {
				result.Index(i).Set(element(filename))
			}
			return result
		}, nil
	case reflect.Func:
		// Parser-installed operator evaluators are immutable functions; the
		// blueprint is built before inference or evaluation can bind clients.
		if typeOf != reflect.TypeFor[BinaryOperatorEvaluator]() {
			return nil, fmt.Errorf("unsupported parse function %s", typeOf)
		}
		function := reflect.New(typeOf).Elem()
		function.Set(value)
		return func(filename reflect.Value) reflect.Value { return function }, nil
	case reflect.String, reflect.Bool, reflect.Int, reflect.Int8, reflect.Int16, reflect.Int32, reflect.Int64,
		reflect.Uint, reflect.Uint8, reflect.Uint16, reflect.Uint32, reflect.Uint64, reflect.Float32, reflect.Float64:
		// Copy scalar values into the blueprint, detached from parser storage.
		scalar := reflect.New(typeOf).Elem()
		scalar.Set(value)
		if value.Kind() == reflect.String {
			*weight += int64(value.Len())
			if *weight > budget {
				return nil, fmt.Errorf("parse blueprint exceeds cache budget")
			}
			// Detach strings from any larger parser source buffer.
			scalar.SetString(strings.Clone(value.String()))
		}
		return func(filename reflect.Value) reflect.Value { return scalar }, nil
	default:
		return nil, fmt.Errorf("unsupported parse field %s", typeOf)
	}
}
