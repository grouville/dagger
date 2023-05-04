package main

import (
	"fmt"

	"github.com/graphql-go/graphql/language/ast"
	"github.com/graphql-go/graphql/language/printer"
)

func main() {
	// Hardcoded string
	data := "This is a test string."

	// Build an *ast.Document containing the string
	doc := &ast.Document{
		Definitions: []ast.Node{
			&ast.OperationDefinition{
				Operation: "query",
				SelectionSet: &ast.SelectionSet{
					Selections: []ast.Selection{
						&ast.Field{
							Name: &ast.Name{
								Value: "someField",
							},
							Arguments: []*ast.Argument{
								{
									Name: &ast.Name{
										Value: "data",
									},
									Value: &ast.StringValue{
										Value: data,
										Kind:  "StringValue", // Set Kind to "StringValue"
									},
								},
							},
						},
					},
				},
			},
		},
	}

	// Print the *ast.Document before printing the query
	fmt.Printf("doc: %+v\n", doc)

	// Print the generated query
	query := printer.Print(doc)
	fmt.Println(query)
}
