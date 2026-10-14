package dagql

import (
	"container/list"
	"context"
	"errors"
	"sync"
)

// This experimental index survives client sessions, not engine restarts.
// Hints select acceleration inputs; callers must still validate them and
// include the selected value in the ordinary recipe identity.
const maxCacheHints = 128

type cacheHintIndex struct {
	mu      sync.Mutex
	entries map[string]*list.Element
	order   list.List
}

type cacheHint struct {
	key     string
	number  uint64
	release func(context.Context) error
}

// SaveCacheHint retains a native result under a caller-scoped key. Replacing
// a hint or exceeding the bounded index releases the previous ownership hold.
func (c *Cache) SaveCacheHint(ctx context.Context, key string, number uint64) error {
	op, err := c.beginCacheOperation()
	if err != nil {
		return err
	}
	defer op.finish(false)
	if err := ctx.Err(); err != nil {
		return err
	}
	_, release, err := c.HoldEntry(ctx, number)
	if err != nil {
		return err
	}

	var previous *cacheHint
	c.cacheHints.mu.Lock()
	if c.closing.Load() {
		c.cacheHints.mu.Unlock()
		return errors.Join(ErrCacheClosed, release(ctx))
	}
	if err := ctx.Err(); err != nil {
		c.cacheHints.mu.Unlock()
		return errors.Join(err, release(ctx))
	}
	if c.cacheHints.entries == nil {
		c.cacheHints.entries = make(map[string]*list.Element)
	}
	if elem := c.cacheHints.entries[key]; elem != nil {
		previous = elem.Value.(*cacheHint)
		c.cacheHints.order.Remove(elem)
	} else if c.cacheHints.order.Len() == maxCacheHints {
		elem := c.cacheHints.order.Back()
		previous = elem.Value.(*cacheHint)
		delete(c.cacheHints.entries, previous.key)
		c.cacheHints.order.Remove(elem)
	}
	c.cacheHints.entries[key] = c.cacheHints.order.PushFront(&cacheHint{key: key, number: number, release: release})
	c.cacheHints.mu.Unlock()
	if previous != nil {
		return previous.release(ctx)
	}
	return nil
}

// LoadCacheHint claims the selected native result for the reading session.
// A temporary hold protects it from concurrent replacement while loading;
// ordinary loading still checks the session's resource requirements.
func (c *Cache) LoadCacheHint(ctx context.Context, key, sessionID string, srv *Server) (res AnyResult, rerr error) {
	op, err := c.beginCacheOperation()
	if err != nil {
		return nil, err
	}
	defer op.finish(false)
	if err := ctx.Err(); err != nil {
		return nil, err
	}
	c.cacheHints.mu.Lock()
	elem := c.cacheHints.entries[key]
	if elem == nil {
		c.cacheHints.mu.Unlock()
		return nil, nil
	}
	hint := elem.Value.(*cacheHint)
	_, release, err := c.HoldEntry(ctx, hint.number)
	if err == nil {
		c.cacheHints.order.MoveToFront(elem)
	}
	c.cacheHints.mu.Unlock()
	if err != nil {
		return nil, err
	}
	defer func() { rerr = errors.Join(rerr, release(ctx)) }()
	return c.LoadResultByResultID(ctx, sessionID, srv, hint.number)
}

func (c *Cache) clearCacheHints(ctx context.Context) error {
	c.cacheHints.mu.Lock()
	hints := c.cacheHints.entries
	c.cacheHints.entries = nil
	c.cacheHints.order.Init()
	c.cacheHints.mu.Unlock()
	var err error
	for _, elem := range hints {
		err = errors.Join(err, elem.Value.(*cacheHint).release(ctx))
	}
	return err
}
