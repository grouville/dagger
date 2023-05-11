package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"log"

	gqlgen "github.com/99designs/gqlgen/graphql"
	"github.com/dagger/graphql"
	"github.com/dagger/graphql/language/ast"
)

var CustomScalarType = graphql.NewScalar(graphql.ScalarConfig{
	Name:        "CustomScalarType",
	Description: "The `CustomScalarType` scalar type represents an ID Object.",
	// Serialize serializes `CustomID` to string.
	Serialize: func(value interface{}) interface{} {
		// fmt.Fprintf(os.Stdout, "Serialize: |%v|\n", value)
		return value
	},
	// ParseValue parses GraphQL variables from `string` to `CustomID`.
	ParseValue: func(value interface{}) interface{} {
		// fmt.Fprintf(os.Stdout, "ParseValue: |%v|\n", value)
		return value
		// switch value := value.(type) {
		// case string:
		// 	return NewCustomID(value)
		// case *string:
		// 	return NewCustomID(*value)
		// default:
		// 	return nil
		// }
	},
	// ParseLiteral parses GraphQL AST value to `CustomID`.
	ParseLiteral: func(valueAST ast.Value) interface{} {
		// fmt.Fprintf(os.Stdout, "ValueAST: |%v|\n", valueAST)
		switch valueAST := valueAST.(type) {
		case *ast.StringValue:
			// fmt.Fprintf(os.Stdout, "ast.StringValue |%v|\n", valueAST.Value)
			return valueAST.Value
		default:
			// fmt.Fprintf(os.Stdout, "default |%v|\n", valueAST)
			return nil
		}
	},
})

var CustomType = graphql.NewObject(graphql.ObjectConfig{
	Name: "Echo",
	Fields: graphql.Fields{
		"result": &graphql.Field{
			Type: CustomScalarType,
		},
	},
})

func main() {
	schema, err := graphql.NewSchema(graphql.SchemaConfig{
		Query: graphql.NewObject(graphql.ObjectConfig{
			Name: "Query",
			Fields: graphql.Fields{
				"echo": &graphql.Field{
					Type: CustomType,
					Args: graphql.FieldConfigArgument{
						&graphql.ArgumentConfig{
							Name: "message",
							Type: CustomScalarType,
						},
					},
					Resolve: func(p graphql.ResolveParams) (interface{}, error) {
						// fmt.Fprintf(os.Stdout, "Resolve: |%v|\n", p)
						content := p.Args["message"]
						// fmt.Fprintf(os.Stdout, "Result from argument: |%v|\n", content)
						// fmt.Fprintf(os.Stdout, "Resolve: Done\n")
						return content, nil
					},
				},
			},
		}),
	})
	if err != nil {
		log.Fatal(err)
	}

	// just resolve
	// query := `query {
	// 	echo {
	// 		result
	// 	}
	// }`

	// ValueAST
	// then resolve
	// query := `query {
	// 	echo(message: "jo") {
	// 		result
	// 	}
	// }`

	// ParseValue
	// then resolve
	queryWithVariable := `
			query($id: CustomScalarType) {
				echo(message: $id) {
					result
				}
			}
		`

	// Query
	// Marshalling the input string
	var byt bytes.Buffer
	gqlgen.MarshalString("jo").MarshalGQL(&byt)
	marshalledInput := byt.String()

	result := graphql.Do(graphql.Params{
		Schema: schema,
		// RequestString: query,
		RequestString: queryWithVariable,
		VariableValues: map[string]interface{}{
			// "id": marshalledInput,
			
			// "message": "to",
			// "id": "to",
		},
	})
	if len(result.Errors) > 0 {
		log.Fatalf("result_error: %+v", result)
	}

	b, err := json.Marshal(result)
	if err != nil {
		log.Fatal(err)
	}

	fmt.Println("result", string(b))
}
