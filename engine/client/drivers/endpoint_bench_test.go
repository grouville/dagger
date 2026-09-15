package drivers

import (
	"bufio"
	"context"
	"net/url"
	"os"
	"testing"
	"time"

	"github.com/stretchr/testify/require"
)

// BenchmarkContainerConnect measures one usable connection to a docker-run
// engine (dial plus the first HTTP round trip, since an exec tunnel is only
// live once the daemon has started the process) over the local endpoint and
// over the exec tunnel it replaces, on the same container. It needs a local
// daemon and an engine image:
//
//	DRIVER_TEST=1 DAGGER_BENCH_ENGINE_IMAGE=registry.dagger.io/engine:v0.21.0 \
//	  go test ./engine/client/drivers -run xxx -bench ContainerConnect -benchtime 20x
func BenchmarkContainerConnect(b *testing.B) {
	if !shouldRun {
		b.Skip("set DRIVER_TEST=1 to run against the local docker daemon")
	}
	image := os.Getenv("DAGGER_BENCH_ENGINE_IMAGE")
	if image == "" {
		b.Skip("set DAGGER_BENCH_ENGINE_IMAGE to the engine image to run")
	}
	ctx := context.Background()
	const name = "dagger-engine-bench-connect"
	target, err := url.Parse("image://" + image)
	require.NoError(b, err)
	target.RawQuery = "container=" + name + "&volume=" + name

	driver := &imageDriver{backend: newDockerAPI()}
	b.Cleanup(func() { _ = driver.backend.ContainerRemove(ctx, name) })
	connector, err := driver.Provision(ctx, target, &DriverOpts{})
	require.NoError(b, err)
	viaEndpoint, ok := connector.(containerConnector)
	require.True(b, ok)
	require.NotNil(b, viaEndpoint.endpoint, "the image driver did not record a local endpoint")
	viaExec := viaEndpoint
	viaExec.endpoint = nil

	// roundTrip opens a connection and waits for the engine's first reply.
	roundTrip := func(c containerConnector) error {
		conn, err := c.Connect(ctx)
		if err != nil {
			return err
		}
		defer conn.Close()
		if _, err := conn.Write([]byte("GET / HTTP/1.0\r\n\r\n")); err != nil {
			return err
		}
		_, err = bufio.NewReader(conn).ReadString('\n')
		return err
	}

	// Wait for the engine to answer before timing anything.
	require.Eventually(b, func() bool { return roundTrip(viaEndpoint) == nil }, 2*time.Minute, 500*time.Millisecond)

	for _, tc := range []struct {
		name string
		c    containerConnector
	}{
		{"endpoint", viaEndpoint},
		{"exec", viaExec},
	} {
		b.Run(tc.name, func(b *testing.B) {
			for range b.N {
				if err := roundTrip(tc.c); err != nil {
					b.Fatal(err)
				}
			}
		})
	}
}
