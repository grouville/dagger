package clientdb

import (
	"bytes"
	"fmt"

	commonpb "go.opentelemetry.io/proto/otlp/common/v1"
	metricpb "go.opentelemetry.io/proto/otlp/metrics/v1"
	resourcepb "go.opentelemetry.io/proto/otlp/resource/v1"
	tracepb "go.opentelemetry.io/proto/otlp/trace/v1"
	"google.golang.org/protobuf/encoding/protojson"
	"google.golang.org/protobuf/proto"
)

// A zero byte cannot begin JSON. Both version and kind are checked before
// decoding, so another message type or a future format cannot become an empty
// successful result through Protobuf's unknown-field handling.
const storedProtoMagic = "\x00PB\x01"

const (
	storedAttributes byte = iota + 1
	storedEvents
	storedLinks
	storedResource
	storedScope
	storedMetrics
)

func storedProtoKind(message proto.Message) (byte, error) {
	switch message.(type) {
	case *resourcepb.Resource:
		return storedResource, nil
	case *commonpb.InstrumentationScope:
		return storedScope, nil
	case *metricpb.ResourceMetrics:
		return storedMetrics, nil
	default:
		return 0, fmt.Errorf("unsupported stored Protobuf message %T", message)
	}
}

func marshalNativeProto(kind byte, message proto.Message) ([]byte, error) {
	buf := make([]byte, len(storedProtoMagic)+1, len(storedProtoMagic)+1+proto.Size(message))
	copy(buf, storedProtoMagic)
	buf[len(storedProtoMagic)] = kind
	return proto.MarshalOptions{}.MarshalAppend(buf, message)
}

func unmarshalNativeProto(data []byte, kind byte, message proto.Message) error {
	if len(data) < len(storedProtoMagic)+1 || string(data[:len(storedProtoMagic)]) != storedProtoMagic {
		return fmt.Errorf("unsupported stored Protobuf header")
	}
	if data[len(storedProtoMagic)] != kind {
		return fmt.Errorf("stored Protobuf kind %d, expected %d", data[len(storedProtoMagic)], kind)
	}
	return proto.Unmarshal(data[len(storedProtoMagic)+1:], message)
}

func isNativeProto(data []byte) bool { return len(data) > 0 && data[0] == 0 }

func emptyNativeProtoList(data []byte, kind byte) bool {
	return len(data) == len(storedProtoMagic)+1 &&
		string(data[:len(storedProtoMagic)]) == storedProtoMagic && data[len(storedProtoMagic)] == kind
}

// MarshalStoredProto encodes a versioned native payload for a telemetry row.
func MarshalStoredProto(message proto.Message) ([]byte, error) {
	kind, err := storedProtoKind(message)
	if err != nil {
		return nil, err
	}
	return marshalNativeProto(kind, message)
}

// UnmarshalStoredProto also accepts the JSON records written by older engines.
// Mixed histories remain readable after a store upgrade.
func UnmarshalStoredProto(data []byte, message proto.Message) error {
	if !isNativeProto(data) {
		return protojson.Unmarshal(data, message)
	}
	kind, err := storedProtoKind(message)
	if err != nil {
		return err
	}
	return unmarshalNativeProto(data, kind, message)
}

// MarshalStoredProtos encodes a supported telemetry list using its generated
// Protobuf wrapper, with a version and kind identifying the stored payload.
func MarshalStoredProtos[T proto.Message](messages []T) ([]byte, error) {
	switch list := any(messages).(type) {
	case []*commonpb.KeyValue:
		return marshalNativeProto(storedAttributes, &commonpb.KeyValueList{Values: list})
	case []*tracepb.Span_Event:
		return marshalNativeProto(storedEvents, &tracepb.Span{Events: list})
	case []*tracepb.Span_Link:
		return marshalNativeProto(storedLinks, &tracepb.Span{Links: list})
	default:
		return nil, fmt.Errorf("unsupported stored Protobuf list %T", messages)
	}
}

// UnmarshalStoredProtos reads native lists and legacy JSON attribute arrays.
func UnmarshalStoredProtos[T proto.Message](data []byte, base T, out *[]T) error {
	if !isNativeProto(data) {
		return UnmarshalProtoJSONs(data, base, out)
	}
	switch list := any(out).(type) {
	case *[]*commonpb.KeyValue:
		var decoded commonpb.KeyValueList
		if err := unmarshalNativeProto(data, storedAttributes, &decoded); err != nil {
			return err
		}
		if decoded.Values == nil {
			decoded.Values = []*commonpb.KeyValue{}
		}
		*list = decoded.Values
	case *[]*tracepb.Span_Event:
		var decoded tracepb.Span
		if err := unmarshalNativeProto(data, storedEvents, &decoded); err != nil {
			return err
		}
		if decoded.Events == nil {
			decoded.Events = []*tracepb.Span_Event{}
		}
		*list = decoded.Events
	case *[]*tracepb.Span_Link:
		var decoded tracepb.Span
		if err := unmarshalNativeProto(data, storedLinks, &decoded); err != nil {
			return err
		}
		if decoded.Links == nil {
			decoded.Links = []*tracepb.Span_Link{}
		}
		*list = decoded.Links
	default:
		return fmt.Errorf("unsupported stored Protobuf list %T", out)
	}
	return nil
}

// Marker scans are only prefilters. False positives can load an extra row;
// keys and values are validated by the readers that consume the row.
func storedProtoContains(data, quotedMarker []byte) bool {
	if isNativeProto(data) && len(quotedMarker) >= 2 {
		return bytes.Contains(data, quotedMarker[1:len(quotedMarker)-1])
	}
	return bytes.Contains(data, quotedMarker)
}

func storedProtoStringAttr(data, quotedKey []byte) (string, bool) {
	if !isNativeProto(data) {
		return protoJSONStringAttr(data, quotedKey)
	}
	var list commonpb.KeyValueList
	if err := unmarshalNativeProto(data, storedAttributes, &list); err != nil {
		return "", false
	}
	key := string(quotedKey[1 : len(quotedKey)-1])
	for _, attr := range list.Values {
		if attr.GetKey() == key {
			value, ok := attr.GetValue().GetValue().(*commonpb.AnyValue_StringValue)
			if !ok {
				return "", false
			}
			return value.StringValue, true
		}
	}
	return "", false
}

func supportedStoreVersion(version byte) bool { return version == 1 || version == storeFormatVersion }
