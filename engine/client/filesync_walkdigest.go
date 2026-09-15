package client

import (
	"crypto/sha256"
	"encoding/binary"
	"encoding/hex"
	"hash"

	"github.com/dagger/dagger/internal/fsutil"
	fstypes "github.com/dagger/dagger/internal/fsutil/types"
)

// walkDigestBufferLimit bounds how many stats are held back while the walk
// digest is undecided. Past it the stream degrades to a plain sync.
const walkDigestBufferLimit = 1 << 20

// walkDigestStream sits between fsutil.Send and the engine. It holds the stat
// stream back until the walk ends, hashing every stat the way the engine's
// differ compares them. If the digest equals the one the engine announced it
// sends one PACKET_UNCHANGED instead of the stats; otherwise it flushes them
// and reports the digest in the terminating stat packet so the engine can
// record it next to the resulting snapshot.
type walkDigestStream struct {
	fsutil.Stream
	known    string
	h        hash.Hash
	buffered []*fstypes.Packet
	decided  bool
}

func newWalkDigestStream(stream fsutil.Stream, known string) *walkDigestStream {
	return &walkDigestStream{Stream: stream, known: known, h: sha256.New()}
}

func (s *walkDigestStream) SendMsg(m any) error {
	if s.decided {
		return s.Stream.SendMsg(m)
	}
	pkt, ok := m.(*fstypes.Packet)
	if !ok || pkt.Type != fstypes.PACKET_STAT {
		// Anything else ends the walk phase; keep ordering intact.
		if err := s.flush(); err != nil {
			return err
		}
		return s.Stream.SendMsg(m)
	}
	if pkt.Stat != nil {
		hashWalkStat(s.h, pkt.Stat)
		s.buffered = append(s.buffered, pkt)
		if len(s.buffered) >= walkDigestBufferLimit {
			return s.flush()
		}
		return nil
	}
	// The terminating stat packet: the walk is complete.
	digest := hex.EncodeToString(s.h.Sum(nil))
	s.decided = true
	if s.known != "" && digest == s.known {
		s.buffered = nil
		return s.Stream.SendMsg(&fstypes.Packet{Type: fstypes.PACKET_UNCHANGED})
	}
	for _, p := range s.buffered {
		if err := s.Stream.SendMsg(p); err != nil {
			return err
		}
	}
	s.buffered = nil
	return s.Stream.SendMsg(&fstypes.Packet{Type: fstypes.PACKET_STAT, Data: []byte(digest)})
}

// flush gives up on deciding and forwards what was held back.
func (s *walkDigestStream) flush() error {
	s.decided = true
	for _, p := range s.buffered {
		if err := s.Stream.SendMsg(p); err != nil {
			return err
		}
	}
	s.buffered = nil
	return nil
}

// hashWalkStat feeds the fields the engine's differ compares (see
// engine/filesync sameFile) plus the path and gitignore marker. Directory
// size and mtime are skipped there too, so a file added inside a directory
// shows up as its own path rather than through its parent.
func hashWalkStat(h hash.Hash, st *fstypes.Stat) {
	writeString := func(v string) {
		var n [8]byte
		binary.LittleEndian.PutUint64(n[:], uint64(len(v)))
		h.Write(n[:])
		h.Write([]byte(v))
	}
	writeInt := func(v int64) {
		var n [8]byte
		binary.LittleEndian.PutUint64(n[:], uint64(v))
		h.Write(n[:])
	}
	writeString(st.Path)
	writeInt(int64(st.Mode))
	writeInt(int64(st.Uid))
	writeInt(int64(st.Gid))
	writeInt(st.Devmajor)
	writeInt(st.Devminor)
	writeString(st.Linkname)
	if !st.IsDir() {
		writeInt(st.Size_)
		writeInt(st.ModTime)
	}
	if st.GitIgnored {
		h.Write([]byte{1})
	} else {
		h.Write([]byte{0})
	}
}
