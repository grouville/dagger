package dangv2

import (
	"bytes"
	"encoding/json"

	bufferjson "github.com/segmentio/encoding/json"
)

// decodeCallJSON keeps numbers exact and decodes one value, as Decoder.Decode
// does. Inputs already reside in memory; parsing them directly avoids a second
// growing read buffer. Default copy flags keep decoded strings private.
func decodeCallJSON(data []byte, dest any) error {
	if _, err := bufferjson.Parse(data, dest, bufferjson.UseNumber); err == nil {
		return nil
	}
	// Keep the existing error types, offsets and messages for invalid inputs.
	decoder := json.NewDecoder(bytes.NewReader(data))
	decoder.UseNumber()
	return decoder.Decode(dest)
}
