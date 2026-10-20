package daggercmd

import (
	"bytes"
	"context"
	"fmt"
	"io"
	"strings"
	"sync"
	"testing"
	"time"

	telemetry "github.com/dagger/otel-go"
	"github.com/spf13/cobra"
	"github.com/stretchr/testify/require"
	logapi "go.opentelemetry.io/otel/log"
	sdklog "go.opentelemetry.io/otel/sdk/log"
)

// A table is emitted through SpanStdio, where each Write becomes a log record.
// Hold the exporter while rendering to reproduce a burst that exceeds the
// default SDK queue, independently of network or scheduler timing.
func TestArtifactListOutputSurvivesLogBurst(t *testing.T) {
	for _, format := range []string{"table", "link", "cli"} {
		t.Run(format, func(t *testing.T) {
			exporter := &heldListLogExporter{started: make(chan struct{}), release: make(chan struct{})}
			provider := sdklog.NewLoggerProvider(sdklog.WithProcessor(sdklog.NewBatchProcessor(exporter,
				sdklog.WithMaxQueueSize(2048),
				sdklog.WithExportMaxBatchSize(1),
			)))
			var release sync.Once
			drain := func() {
				release.Do(func() { close(exporter.release) })
				ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
				defer cancel()
				require.NoError(t, provider.Shutdown(ctx))
			}
			t.Cleanup(drain)
			ctx := telemetry.WithLoggerProvider(t.Context(), provider)
			// Occupy the exporter before the actual output starts.
			provider.Logger("test").Emit(ctx, logapi.Record{})
			select {
			case <-exporter.started:
			case <-time.After(10 * time.Second):
				t.Fatal("exporter did not start")
			}

			const count = 4096
			items := listedPackages(count)
			cmd := &cobra.Command{Use: "check"}
			registerArtifactListFlags(cmd)
			cmd.Flags().String("format", format, "")
			cmd.SetOut(telemetry.NewWriter(ctx, "test"))
			names := map[string]string{"module": "module", "go/packages": "go-package", "type:Check": "check"}
			require.NoError(t, writeArtifactList(cmd, items, names))
			drain()

			lines := strings.Split(strings.TrimSpace(exporter.output.String()), "\n")
			expectedLines := count
			offset := 0
			if format == "table" {
				expectedLines++ // header
				offset = 1
			}
			require.Equal(t, expectedLines, len(lines), "listing output was lost in the telemetry queue")
			for i := range count {
				require.Contains(t, lines[i+offset], fmt.Sprintf("pkg_%04d", i))
			}
		})
	}
}

func TestArtifactListOutputWriteError(t *testing.T) {
	for _, format := range []string{"table", "link", "cli"} {
		t.Run(format, func(t *testing.T) {
			for _, count := range []int{1, 4096} {
				r, w := io.Pipe()
				require.NoError(t, r.Close())
				t.Cleanup(func() { _ = w.Close() })
				cmd := &cobra.Command{Use: "check"}
				registerArtifactListFlags(cmd)
				cmd.Flags().String("format", format, "")
				cmd.SetOut(w)
				require.ErrorIs(t, writeArtifactList(cmd, listedPackages(count), nil), io.ErrClosedPipe)
			}
		})
	}
}

func listedPackages(count int) []listedArtifact {
	items := make([]listedArtifact, count)
	for i := range items {
		name := fmt.Sprintf("pkg_%04d", i)
		items[i] = listedArtifact{
			URI: "dag+check://go/packages/check?go-package=" + name,
			DimensionKeys: []struct{ Dimension, Key string }{
				{"module", "go"}, {"go/packages", name}, {"type:Check", "check"},
			},
		}
	}
	return items
}

type heldListLogExporter struct {
	started chan struct{}
	release chan struct{}
	once    sync.Once
	output  bytes.Buffer
}

func (e *heldListLogExporter) Export(ctx context.Context, records []sdklog.Record) error {
	e.once.Do(func() { close(e.started) })
	select {
	case <-e.release:
	case <-ctx.Done():
		return ctx.Err()
	}
	for _, record := range records {
		if record.Body().Kind() == logapi.KindString {
			e.output.WriteString(record.Body().AsString())
		}
	}
	return nil
}

func (*heldListLogExporter) ForceFlush(context.Context) error { return nil }
func (*heldListLogExporter) Shutdown(context.Context) error   { return nil }
