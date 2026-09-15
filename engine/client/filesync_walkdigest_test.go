package client

import (
	"context"
	"os"
	"testing"

	fstypes "github.com/dagger/dagger/internal/fsutil/types"
	"github.com/stretchr/testify/require"
)

type recordingStream struct {
	sent []*fstypes.Packet
}

func (s *recordingStream) RecvMsg(any) error        { return nil }
func (s *recordingStream) Context() context.Context { return context.Background() }
func (s *recordingStream) SendMsg(m any) error {
	s.sent = append(s.sent, m.(*fstypes.Packet))
	return nil
}

func statPacket(path string, size, mtime int64) *fstypes.Packet {
	return &fstypes.Packet{Type: fstypes.PACKET_STAT, Stat: &fstypes.Stat{Path: path, Mode: 0o644, Size_: size, ModTime: mtime}}
}

func sendWalk(t *testing.T, known string, pkts ...*fstypes.Packet) []*fstypes.Packet {
	t.Helper()
	rec := &recordingStream{}
	ws := newWalkDigestStream(rec, known)
	for _, p := range pkts {
		require.NoError(t, ws.SendMsg(p))
	}
	require.NoError(t, ws.SendMsg(&fstypes.Packet{Type: fstypes.PACKET_STAT}))
	return rec.sent
}

func TestWalkDigestStream(t *testing.T) {
	a := statPacket("a.txt", 1, 10)
	b := statPacket("dir/b.txt", 2, 20)

	// No known digest: everything is forwarded in order and the terminator
	// reports the digest.
	sent := sendWalk(t, "", a, b)
	require.Len(t, sent, 3)
	require.Same(t, a, sent[0])
	require.Same(t, b, sent[1])
	require.Equal(t, fstypes.PACKET_STAT, sent[2].Type)
	require.Nil(t, sent[2].Stat)
	digest := string(sent[2].Data)
	require.Len(t, digest, 64)

	// The same walk against that digest collapses to one packet.
	sent = sendWalk(t, digest, a, b)
	require.Len(t, sent, 1)
	require.Equal(t, fstypes.PACKET_UNCHANGED, sent[0].Type)

	// Any field the differ compares changes the digest.
	sent = sendWalk(t, digest, a, statPacket("dir/b.txt", 2, 21))
	require.Len(t, sent, 3)
	require.NotEqual(t, digest, string(sent[2].Data))

	// Directory size and mtime are not compared, so they do not change it.
	dir := &fstypes.Packet{Type: fstypes.PACKET_STAT, Stat: &fstypes.Stat{Path: "dir", Mode: uint32(os.ModeDir | 0o755), Size_: 4096, ModTime: 1}}
	sent = sendWalk(t, "", dir, a)
	digest = string(sent[2].Data)
	dir2 := &fstypes.Packet{Type: fstypes.PACKET_STAT, Stat: &fstypes.Stat{Path: "dir", Mode: uint32(os.ModeDir | 0o755), Size_: 8192, ModTime: 2}}
	sent = sendWalk(t, digest, dir2, a)
	require.Len(t, sent, 1)
	require.Equal(t, fstypes.PACKET_UNCHANGED, sent[0].Type)

	// A non-stat packet mid-walk flushes what was held, in order.
	rec := &recordingStream{}
	ws := newWalkDigestStream(rec, digest)
	require.NoError(t, ws.SendMsg(a))
	errPkt := &fstypes.Packet{Type: fstypes.PACKET_ERR, Data: []byte("boom")}
	require.NoError(t, ws.SendMsg(errPkt))
	require.Len(t, rec.sent, 2)
	require.Same(t, a, rec.sent[0])
	require.Same(t, errPkt, rec.sent[1])
}
