package client

import (
	"context"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/dagger/dagger/engine"
	"github.com/dagger/dagger/internal/buildkit/session/filesync"
	fstypes "github.com/dagger/dagger/internal/fsutil/types"
	"github.com/gogo/protobuf/proto"
	"github.com/stretchr/testify/require"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/metadata"
	"google.golang.org/grpc/status"
)

type parentMetadataStream struct {
	grpc.ServerStream
	ctx     context.Context
	sent    chan *fstypes.Packet
	replies chan *fstypes.Packet
}

func (s *parentMetadataStream) Context() context.Context     { return s.ctx }
func (s *parentMetadataStream) Send(p *fstypes.Packet) error { return s.SendMsg(p) }
func (s *parentMetadataStream) Recv() (*fstypes.Packet, error) {
	var p fstypes.Packet
	err := s.RecvMsg(&p)
	return &p, err
}
func (s *parentMetadataStream) SendMsg(v any) error {
	p := proto.Clone(v.(*fstypes.Packet)).(*fstypes.Packet)
	select {
	case s.sent <- p:
		return nil
	case <-s.ctx.Done():
		return s.ctx.Err()
	}
}
func (s *parentMetadataStream) RecvMsg(v any) error {
	select {
	case p := <-s.replies:
		*v.(*fstypes.Packet) = *p
		return nil
	case <-s.ctx.Done():
		return s.ctx.Err()
	}
}

var _ filesync.FileSync_DiffCopyServer = (*parentMetadataStream)(nil)

func parentMetadataWireStream(t *testing.T, opts engine.LocalImportOpts) *parentMetadataStream {
	t.Helper()
	ctx, cancel := context.WithTimeout(t.Context(), 5*time.Second)
	t.Cleanup(cancel)
	return &parentMetadataStream{ctx: metadata.NewIncomingContext(ctx, opts.ToGRPCMD()), sent: make(chan *fstypes.Packet, 32), replies: make(chan *fstypes.Packet, 2)}
}

func TestParentDirectoryMetadataActualDiffCopy(t *testing.T) {
	base, err := filepath.EvalSymlinks(t.TempDir())
	require.NoError(t, err)
	target := filepath.Join(base, "a", "b")
	require.NoError(t, os.MkdirAll(target, 0751))
	require.NoError(t, os.WriteFile(filepath.Join(target, "not-transferred"), []byte("no content packets"), 0600))
	volume := filepath.VolumeName(target)
	rel := strings.TrimPrefix(filepath.ToSlash(strings.TrimPrefix(target, volume)), "/")
	opts := engine.LocalImportOpts{Path: filepath.Clean(volume + string(filepath.Separator)), ParentDirsOnly: true, IncludePatterns: []string{rel}, ExcludePatterns: []string{rel + "/*"}}
	s := parentMetadataWireStream(t, opts)
	decoded, err := engine.LocalImportOptsFromContext(s.ctx)
	require.NoError(t, err)
	require.True(t, decoded.ParentDirsOnly)
	done := make(chan error, 1)
	go func() { done <- (FilesyncSource{}).DiffCopy(s) }()
	var paths []string
	finished := false
	for !finished {
		select {
		case <-s.ctx.Done():
			t.Fatal(s.ctx.Err())
		case p := <-s.sent:
			switch p.Type {
			case fstypes.PACKET_STAT:
				if p.Stat == nil {
					s.replies <- &fstypes.Packet{Type: fstypes.PACKET_FIN}
					continue
				}
				require.True(t, os.FileMode(p.Stat.Mode).IsDir(), "the explicit operation must never emit a content-bearing file")
				require.Zero(t, p.Stat.Uid)
				require.Zero(t, p.Stat.Gid)
				require.Empty(t, p.Stat.Xattrs)
				paths = append(paths, p.Stat.Path)
			case fstypes.PACKET_FIN:
				finished = true
			case fstypes.PACKET_DATA:
				t.Fatal("unexpected file content packet")
			case fstypes.PACKET_ERR:
				t.Fatalf("sender error: %s", p.Data)
			default:
				t.Fatalf("unexpected packet type %v", p.Type)
			}
		}
	}
	require.NoError(t, <-done)
	var want []string
	var part string
	for _, component := range strings.Split(rel, "/") {
		if part == "" {
			part = component
		} else {
			part += "/" + component
		}
		want = append(want, part)
	}
	require.Equal(t, want, paths)
}

func TestParentDirectoryMetadataDiffCopyRejectsBroadening(t *testing.T) {
	for name, opts := range map[string]engine.LocalImportOpts{
		"non-root":          {Path: t.TempDir(), ParentDirsOnly: true, IncludePatterns: []string{"a"}, ExcludePatterns: []string{"a/*"}},
		"escape":            {Path: "/", ParentDirsOnly: true, IncludePatterns: []string{"../a"}, ExcludePatterns: []string{"../a/*"}},
		"negated-exclusion": {Path: "/", ParentDirsOnly: true, IncludePatterns: []string{"a"}, ExcludePatterns: []string{"a/*", "!a/private"}},
		"mixed-stat":        {Path: "/", ParentDirsOnly: true, StatPathOnly: true, IncludePatterns: []string{"a"}, ExcludePatterns: []string{"a/*"}},
	} {
		t.Run(name, func(t *testing.T) {
			s := parentMetadataWireStream(t, opts)
			err := (FilesyncSource{}).DiffCopy(s)
			require.Equal(t, codes.InvalidArgument, status.Code(err))
			require.Empty(t, s.sent)
		})
	}
}

// The error packet is the first-divergence witness: the ordinary filtered
// walk suppresses a missing literal target, but this explicit metadata
// operation must report it instead of accepting an incomplete parent chain.
func TestParentDirectoryMetadataMissingDispatchWitness(t *testing.T) {
	base, err := filepath.EvalSymlinks(t.TempDir())
	require.NoError(t, err)
	target := filepath.Join(base, "missing")
	volume := filepath.VolumeName(target)
	rel := strings.TrimPrefix(filepath.ToSlash(strings.TrimPrefix(target, volume)), "/")
	opts := engine.LocalImportOpts{Path: filepath.Clean(volume + string(filepath.Separator)), ParentDirsOnly: true, IncludePatterns: []string{rel}, ExcludePatterns: []string{rel + "/*"}}
	s := parentMetadataWireStream(t, opts)
	done := make(chan error, 1)
	go func() { done <- (FilesyncSource{}).DiffCopy(s) }()
	select {
	case <-s.ctx.Done():
		t.Fatal(s.ctx.Err())
	case p := <-s.sent:
		require.Equal(t, fstypes.PACKET_ERR, p.Type)
		require.Nil(t, p.Stat)
	}
	s.replies <- &fstypes.Packet{Type: fstypes.PACKET_FIN}
	require.Error(t, <-done)
}
