package drivers

import "context"

// containerState is a point-in-time observation, not a liveness guarantee.
// running defaults to false for backends that only support existence checks.
type containerState struct {
	exists  bool
	running bool
}

type containerStateBackend interface {
	ContainerState(context.Context, string) (containerState, error)
}

func lookupContainerState(ctx context.Context, backend containerBackend, name string) (containerState, error) {
	if backend, ok := backend.(containerStateBackend); ok {
		return backend.ContainerState(ctx, name)
	}
	exists, err := backend.ContainerExists(ctx, name)
	return containerState{exists: exists}, err
}
