package schema

// Git Lazy Resolution
//
// Git operations are lazy: git("github.com/foo").branch("main") doesn't hit the network.
// Resolution happens when you call tree(), commit(), etc. At that point, we may discover
// the URL needs a protocol prefix (https://) or auth injection (SSH socket, HTTP token).
//
// When resolution changes the receiver (e.g., "github.com/foo" → "https://github.com/foo"),
// we must "redirect" the entire call chain to the corrected receiver so the cache keys match.
// This is similar to an HTTP redirect: same request, different base URL.
//
// Example:
//
//	Original:  git("github.com/foo").branch("main").tree()
//	Resolved:  git("https://github.com/foo").branch("main").tree()
//
// The redirect* helpers rebuild and load the call chain on the resolved receiver.

import (
	"context"
	"fmt"

	"github.com/dagger/dagger/core"
	"github.com/dagger/dagger/dagql"
	"github.com/dagger/dagger/dagql/call"
)

// resolveField is the dagql field name for lazy resolution.
const resolveField = "__resolve"

// alreadyResolved returns true if this object was already resolved (prevents infinite recursion).
// If the parent's field is __resolve, we've been redirected here and shouldn't resolve again.
func alreadyResolved(id *call.ID) bool {
	return id.Field() == resolveField
}

// receiverChanged returns true if resolution produced a different receiver.
// resolved.ID() is always "original.__resolve" or "newReceiver.__resolve".
// We compare the receiver (the object before __resolve) with the original.
func receiverChanged[T dagql.Typed](resolved, original dagql.ObjectResult[T]) bool {
	return resolved.ID().Receiver().Digest() != original.ID().Digest()
}

// redirect works like an HTTP 301 redirect.
//
// Instead of computing the result here, we tell dagql: "go execute this call
// on the canonical receiver instead." This ensures the result is cached under
// the canonical cache key, so future calls (regardless of how the URL was
// originally written) will hit the same cache entry.
//
// Example:
//
//	git("github.com/foo").url() is called
//	  → resolution canonicalizes to git("https://github.com/foo", sshAuthSocket: X)
//	  → redirect says "go execute git("https://...").url() instead"
//	  → result is cached under git("https://...").url()
//	  → future calls to git("https://...").url() get a cache hit
func redirect[T dagql.Typed](
	ctx context.Context,
	resolvedReceiverID *call.ID,
) (dagql.ObjectResult[T], error) {
	var zero dagql.ObjectResult[T]

	srv, err := core.CurrentDagqlServer(ctx)
	if err != nil {
		return zero, fmt.Errorf("failed to get current dagql server: %w", err)
	}

	// Get the current operation (e.g., "url" from git("...").url())
	opToReplay := dagql.CurrentID(ctx)

	// Build the redirected call: canonicalReceiver.currentOp()
	// e.g., git("github.com/foo").url() → git("https://github.com/foo").url()
	redirectedID := resolvedReceiverID.Append(
		opToReplay.Type().ToAST(), // return type
		opToReplay.Field(),        // field name (e.g., "url")
		call.WithArgs(opToReplay.Args()...),
		call.WithView(opToReplay.View()),
	)

	result, err := srv.Load(ctx, redirectedID)
	if err != nil {
		return zero, err
	}
	return result.(dagql.ObjectResult[T]), nil
}

// redirectScalar is like redirect but for scalar return types.
func redirectScalar[T any](
	ctx context.Context,
	resolvedReceiverID *call.ID,
) (T, error) {
	var zero T

	srv, err := core.CurrentDagqlServer(ctx)
	if err != nil {
		return zero, fmt.Errorf("failed to get current dagql server: %w", err)
	}

	opToReplay := dagql.CurrentID(ctx)

	redirectedID := resolvedReceiverID.Append(
		opToReplay.Type().ToAST(),
		opToReplay.Field(),
		call.WithArgs(opToReplay.Args()...),
		call.WithView(opToReplay.View()),
	)

	result, err := srv.LoadType(ctx, redirectedID)
	if err != nil {
		return zero, err
	}
	return result.Unwrap().(T), nil
}

// redirectThroughRef is like redirect but for 2-level deep calls (Git-specific).
//
// Why is this needed? When resolving a GitRef, we first resolve the underlying
// repo. If the repo changes (e.g., adds auth), we can't use plain redirect()
// because that only replays ONE operation. Here we have TWO levels:
//
//	git("github.com/foo").branch("main").__resolve
//	         ↑ repo              ↑ ref       ↑ leaf (current op)
//
// If just the repo changed, redirect() would try: newRepo.__resolve
// But we need: newRepo.branch("main").__resolve
//
// So redirectThroughRef rebuilds both the ref AND the leaf on the canonical repo:
//
//	BEFORE: git("github.com/foo").branch("main").__resolve
//	AFTER:  git("https://github.com/foo").branch("main").__resolve
func redirectThroughRef[T dagql.Typed](
	ctx context.Context,
	resolvedRepoID *call.ID,
	refOpToReplay *call.ID,
) (dagql.ObjectResult[T], error) {
	var zero dagql.ObjectResult[T]

	srv, err := core.CurrentDagqlServer(ctx)
	if err != nil {
		return zero, fmt.Errorf("failed to get current dagql server: %w", err)
	}

	// Get the leaf operation we're currently in (e.g., __resolve, tree, commit)
	leafOpToReplay := dagql.CurrentID(ctx)

	// Step 1: Rebuild the ref on the canonical repo
	// git("https://github.com/foo").branch("main")
	rebuiltRefID := resolvedRepoID.Append(
		(*core.GitRef)(nil).Type(),
		refOpToReplay.Field(), // "branch", "tag", etc.
		call.WithArgs(refOpToReplay.Args()...),
		call.WithView(refOpToReplay.View()),
	)

	// Step 2: Append the leaf operation to the rebuilt ref
	// git("https://github.com/foo").branch("main").__resolve
	redirectedID := rebuiltRefID.Append(
		leafOpToReplay.Type().ToAST(),
		leafOpToReplay.Field(), // "__resolve", "tree", etc.
		call.WithArgs(leafOpToReplay.Args()...),
		call.WithView(refOpToReplay.View()),
	)

	result, err := srv.Load(ctx, redirectedID)
	if err != nil {
		return zero, err
	}
	return result.(dagql.ObjectResult[T]), nil
}

// injectedAuth holds the result of auth detection.
type injectedAuth struct {
	urlOverride string
	extraArgs   []dagql.NamedInput
}
