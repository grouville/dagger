package main

import (
	"bytes"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"log"

	"github.com/dagger/graphql"
	"github.com/dagger/graphql/language/ast"
)

var BinaryScalarType = graphql.NewScalar(graphql.ScalarConfig{
	Name:        "Binary",
	Description: "The `Binary` scalar type represents binary data as Base64 encoded strings.",
	Serialize: func(value interface{}) interface{} {
		switch value := value.(type) {
		case []byte:
			// fmt.Printf("Serialize: |%s|\n", value)
			return base64.StdEncoding.EncodeToString(value)
			// return string(value)
		default:
			return nil
		}
	},
	ParseValue: func(value interface{}) interface{} {
		switch value := value.(type) {
		case string:
			data, err := base64.StdEncoding.DecodeString(value)
			if err != nil {
				return nil
			}
			fmt.Printf("ParseValue: |%s|\n", data)
			// return string(data)
			return data
		default:
			return nil
		}
	},
	ParseLiteral: func(valueAST ast.Value) interface{} {
		switch valueAST := valueAST.(type) {
		case *ast.StringValue:
			data, err := base64.StdEncoding.DecodeString(valueAST.Value)
			if err != nil {
				return nil
			}
			fmt.Printf("ParseLiteral: |%x|\n", data)
			return data
		default:
			return nil
		}
	},
})

var originalString []byte
var data string

var QueryType = graphql.NewObject(graphql.ObjectConfig{
	Name: "Query",
	Fields: graphql.Fields{
		"echo": &graphql.Field{
			Type: BinaryScalarType,
			Args: graphql.FieldConfigArgument{
				&graphql.ArgumentConfig{
					Name: "message",
					Type: BinaryScalarType,
				},
			},
			Resolve: func(p graphql.ResolveParams) (interface{}, error) {
				fmt.Printf("Resolve %s\n", p.Args)
				message, ok := p.Args["message"].([]byte)
				if ok {
					// Comparing the incoming data to the original data
					if !bytes.Equal(message, []byte(originalString)) {
						fmt.Printf("Incoming data does not match original data!: %q\n%q\n", string(message), data)
					} else {
						fmt.Printf("Incoming data matches original data: %x|%x")
					}
					// Simply echo the message back.
					// In a real scenario, you could do something more interesting here.
					return message, nil
				}
				return nil, nil
			},
		},
	},
})

func main() {
	// filePath := "/Users/home/.gnupg/trustdb.gpg"

	// originalString, _ = ioutil.ReadFile(filePath)
	// if err != nil {
	// 	panic(err)
	// }

	originalString = []byte("jo")
	data = base64.StdEncoding.EncodeToString(originalString)

	schema, err := graphql.NewSchema(graphql.SchemaConfig{
		Query: QueryType,
	})
	if err != nil {
		log.Fatalf("failed to create new schema, error: %v", err)
	}

	query := fmt.Sprintf(`
	{
		echo(message: "%s")
	}
	`, data)

	params := graphql.Params{Schema: schema, RequestString: query}
	r := graphql.Do(params)
	if len(r.Errors) > 0 {
		log.Fatalf("failed to execute graphql operation, errors: %+v", r.Errors)
	}

	// Unmarshal the response
	b, err := json.Marshal(r)
	if err != nil {
		log.Fatal(err)
	}

	var ro map[string]interface{}
	if err := json.Unmarshal(b, &ro); err != nil {
		log.Fatalf("failed to unmarshal response: %v", err)
	}
	// fmt.Println("result", string(b))

	data, _ := ro["data"].(map[string]interface{})
	echo, _ := data["echo"].(string)
	fmt.Println("Echo:", echo)
}
