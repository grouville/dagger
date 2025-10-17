package templates_test

import (
	"bytes"
	"encoding/json"
	"testing"

	"github.com/stretchr/testify/require"

	"github.com/dagger/dagger/cmd/codegen/generator"
	"github.com/dagger/dagger/cmd/codegen/introspection"
)

func TestObjectBasic(t *testing.T) {
	tmpl := templateHelper(t)

	var obj introspection.Type
	err := json.Unmarshal([]byte(containerExecArgsJSON), &obj)
	require.NoError(t, err)

	schema := introspection.Schema{Types: []*introspection.Type{&obj}}
	generator.SetSchemaParents(&schema)

	var b bytes.Buffer
	err = tmpl.ExecuteTemplate(&b, "object", &obj)
	require.NoError(t, err)

	want := updateAndGetFixtures(t, "testdata/object_container_want.py", b.String())
	require.Equal(t, want, b.String())
}

var containerExecArgsJSON = `
{
  "kind": "OBJECT",
  "name": "Container",
  "description": "",
  "fields": [
    {
      "name": "exec",
      "description": "",
      "args": [
        {
          "name": "args",
          "description": "",
          "type": {
            "kind": "LIST",
            "name": null,
            "ofType": {
              "kind": "NON_NULL",
              "name": null,
              "ofType": { "kind": "SCALAR", "name": "String", "ofType": null }
            }
          },
          "defaultValue": null
        },
        {
          "name": "stdin",
          "description": "",
          "type": { "kind": "SCALAR", "name": "String", "ofType": null },
          "defaultValue": null
        }
      ],
      "type": {
        "kind": "NON_NULL",
        "name": null,
        "ofType": { "kind": "OBJECT", "name": "Container", "ofType": null }
      },
      "isDeprecated": false,
      "deprecationReason": null
    }
  ],
  "inputFields": null,
  "interfaces": [],
  "enumValues": null,
  "possibleTypes": null
}
`
