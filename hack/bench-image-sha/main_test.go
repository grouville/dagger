package main

import (
	"bytes"
	"crypto/sha256"
	"encoding"
	"encoding/hex"
	"testing"
)

func TestKnownVectors(t *testing.T) {
	for _, tc := range []struct{ data, sum string }{
		{"", "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"},
		{"abc", "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"},
		{"abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq", "248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1"},
	} {
		h := sha256.New()
		for i := range len(tc.data) {
			h.Write([]byte(tc.data[i : i+1]))
		}
		if got := hex.EncodeToString(h.Sum(nil)); got != tc.sum {
			t.Fatalf("vector length %d: %s", len(tc.data), got)
		}
	}
}

func TestChunksSumAndReset(t *testing.T) {
	for _, n := range []int{0, 1, 55, 56, 63, 64, 65, 255, 256*1024 - 1, 256 * 1024, 256*1024 + 1, 1024*1024 + 3} {
		data := make([]byte, n)
		for i := range data {
			data[i] = byte(i*37 + i/251)
		}
		want := sha256.Sum256(data)
		for _, step := range []int{1, 63, 64, 65, 256 * 1024} {
			h := sha256.New()
			for off := 0; off < n; off += step {
				h.Write(data[off:min(off+step, n)])
				if off < 128 { // Sum must not consume the ongoing state.
					h.Sum(nil)
				}
			}
			if !bytes.Equal(h.Sum(nil), want[:]) {
				t.Fatalf("length %d step %d", n, step)
			}
			h.Reset()
			h.Write(data)
			if !bytes.Equal(h.Sum(nil), want[:]) {
				t.Fatalf("reset length %d step %d", n, step)
			}
		}
	}
}

func TestResumeState(t *testing.T) {
	data := bytes.Repeat([]byte("same complete SHA256 message; no digest algorithm change"), 1501)
	want := sha256.Sum256(data)
	for _, split := range []int{0, 1, 63, 64, 65, 1001, len(data)} {
		h := sha256.New()
		h.Write(data[:split])
		state, err := h.(encoding.BinaryMarshaler).MarshalBinary()
		if err != nil {
			t.Fatal(err)
		}
		resumed := sha256.New()
		if err := resumed.(encoding.BinaryUnmarshaler).UnmarshalBinary(state); err != nil {
			t.Fatal(err)
		}
		resumed.Write(data[split:])
		if !bytes.Equal(resumed.Sum(nil), want[:]) {
			t.Fatalf("resume split %d", split)
		}
	}
}
