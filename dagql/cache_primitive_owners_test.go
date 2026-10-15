package dagql

import (
	"context"
	"fmt"
	"testing"

	"github.com/stretchr/testify/require"
	"github.com/vektah/gqlparser/v2/ast"
)

// A scalar's schema name does not establish that its Go value has no owners.
type inlineStringOwner struct {
	String
	host     *PartHost
	released int
}

func (*inlineStringOwner) Type() *ast.Type { return String("").Type() }
func (*inlineStringOwner) PersistedSnapshotRefLinks() []PersistedSnapshotRefLink {
	return []PersistedSnapshotRefLink{{Role: "snapshot", RefKey: "owned"}}
}
func (v *inlineStringOwner) BindPartHost(host *PartHost) { v.host = host }
func (v *inlineStringOwner) OnRelease(context.Context) error {
	v.released++
	return nil
}

func TestInlinePrimitiveNamedOwner(t *testing.T) {
	value := &inlineStringOwner{String: "value"}
	self := Array[*inlineStringOwner]{value}
	frame := persistCodecFrame("inline", self)
	wantPath := PersistedRefPath{}.Field("items").Index(0)
	links, err := collectSnapshotOwnerLinks(t.Context(), self, frame, false)
	require.NoError(t, err)
	require.Equal(t, []PersistedSnapshotRefLink{{Role: "snapshot", RefKey: "owned", OutputPath: wantPath}}, links)

	res := newDetachedResult(frame, self)
	c := &Cache{}
	require.NoError(t, c.attachInlineHosts(res.shared, res))
	require.NotNil(t, value.host)
	require.Same(t, res.shared, value.host.row)
	require.Equal(t, wantPath, value.host.path)
	require.NotNil(t, res.shared.onRelease)
	require.NoError(t, res.shared.onRelease(t.Context()))
	require.Equal(t, 1, value.released)
}

func TestPrimitiveArrayRequiresListDeclaration(t *testing.T) {
	self := NewStringArray("value")
	for _, frame := range []*ResultCall{nil, {Type: NewResultCallType(String("").Type())}} {
		_, err := collectSnapshotOwnerLinks(t.Context(), self, frame, false)
		require.ErrorContains(t, err, "missing authoritative list call")
	}
}

// A bulk call often has as many input paths as output values. Ownership walks
// should not copy the entire input list for every primitive output element.
func BenchmarkPrimitiveArrayOwners(b *testing.B) {
	for _, size := range []int{128, 512, 1024} {
		b.Run(fmt.Sprint(size), func(b *testing.B) {
			values := make(Array[String], size)
			inputs := make([]*ResultCallLiteral, size)
			for i := range size {
				values[i] = String(fmt.Sprintf("digest-%d", i))
				inputs[i] = &ResultCallLiteral{Kind: ResultCallLiteralKindString, StringValue: fmt.Sprintf("crate_%04d", i)}
			}
			frame := persistCodecFrame("digests", values)
			frame.Args = []*ResultCallArg{{Name: "paths", Value: &ResultCallLiteral{Kind: ResultCallLiteralKindList, ListItems: inputs}}}
			b.Run("snapshot_links", func(b *testing.B) {
				b.ReportAllocs()
				for b.Loop() {
					links, err := collectSnapshotOwnerLinks(b.Context(), values, frame, false)
					if err != nil || len(links) != 0 {
						b.Fatalf("links=%v, error=%v", links, err)
					}
				}
			})
			b.Run("part_hosts", func(b *testing.B) {
				res := newDetachedResult(frame, values)
				c := &Cache{}
				b.ReportAllocs()
				for b.Loop() {
					if err := c.attachInlineHosts(res.shared, res); err != nil {
						b.Fatal(err)
					}
				}
			})
		})
	}
}
