package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"io/ioutil"
	"log"
	"net/http"
	"net/url"

	"github.com/99designs/gqlgen/graphql"
	// "unicode/utf16"
)

type GraphQLRequest struct {
	Query string `json:"query"`
}

func sendGraphQLRequest(url string, query string) (string, error) {
	payload := GraphQLRequest{Query: query}

	jsonData, err := json.Marshal(payload)
	if err != nil {
		return "", err
	}

	resp, err := http.Post(url, "application/json", bytes.NewBuffer(jsonData))
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()

	body, err := ioutil.ReadAll(resp.Body)
	if err != nil {
		return "", err
	}

	return string(body), nil
}

// func isSurrogate(r rune) bool {
// 	return 0xD800 <= r && r <= 0xDFFF
// }

// func escapeGraphQLString(input string) string {

// }
// 	var escapeBuffer bytes.Buffer
// 	blockString := false

// 	if len(input) >= 3 && input[:3] == `"""` {
// 		blockString = true
// 	}

// 	for _, r := range input {
// 		switch {
// 		case r == '\t':
// 			escapeBuffer.WriteString(`\t`)
// 		case r == '\r':
// 			escapeBuffer.WriteString(`\r`)
// 		case r == '\n':
// 			if !blockString {
// 				escapeBuffer.WriteString(`\n`)
// 			} else {
// 				escapeBuffer.WriteRune(r)
// 			}
// 		case r == '\\':
// 			escapeBuffer.WriteString(`\\`)
// 		case r == '"':
// 			if !blockString {
// 				escapeBuffer.WriteString(`\"`)
// 			} else {
// 				escapeBuffer.WriteRune(r)
// 			}
// 		case (r >= 0 && r <= 0x1F) || (r >= 0x7F && r <= 0x9F):
// 			if r <= 0xFFFF {
// 				escapeBuffer.WriteString(fmt.Sprintf(`\u%04X`, r))
// 			} else {
// 				r1, r2 := utf16.EncodeRune(r)
// 				escapeBuffer.WriteString(fmt.Sprintf(`\u%04X\u%04X`, r1, r2))
// 			}
// 		default:
// 			escapeBuffer.WriteRune(r)
// 		}
// 	}

// 	return escapeBuffer.String()
// }

type graphqlResponse struct {
	Data struct {
		Echo string `json:"echo"`
	} `json:"data"`
}

type Marshaler interface {
	MarshalGQL(w io.Writer)
}

func m2s(m Marshaler) string {
	var b bytes.Buffer
	m.MarshalGQL(&b)
	return b.String()
}

func main() {
	// filePath := "/Users/home/.gnupg/trustdb.gpg"
	filePath := "/Users/home/.gnupg/pubring.kbx"
	content, err := ioutil.ReadFile(filePath)
	if err != nil {
		fmt.Println("Error reading file:", err)
		return
	}

	input := string(content)
	// escapedInput := escapeGraphQLString(input)
	escapedInput := input

	var b bytes.Buffer
	graphql.MarshalString(fmt.Sprintf(`{ echo(text: "%s") }`, escapedInput)).MarshalGQL(&b)
	// query := graphql.MarshalString(fmt.Sprintf(`{ echo(text: "%s") }`, escapedInput)).MarshalGQL()

	resp, err := http.Get("http://localhost:8080/graphql?query=" + url.QueryEscape(b.String()))
	if err != nil {
		log.Fatalf("Error sending query: %v", err)

	}
	defer resp.Body.Close()

	body, err := ioutil.ReadAll(resp.Body)
	if err != nil {
		log.Fatalf("Error reading response body: %v", err)
	}

	var result graphqlResponse
	err = json.Unmarshal(body, &result)
	if err != nil {
		log.Fatalf("Error unmarshaling response: %v", err)
	}

	fmt.Println("Response:", result)
}
