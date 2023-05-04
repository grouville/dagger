package main

import (
	"encoding/json"
	"fmt"
	"io/ioutil"
	"net/http"
	"net/url"
	"testing"
)

func TestEscapeGraphQLString(t *testing.T) {
	testCases := []struct {
		input string
	}{
		// ASCII control characters
		{"\b"},
		{"\f"},
		{"\n"},
		{"\r"},
		{"\t"},

		// Escaped character
		{"\""},
		{"\\"},
		{"/"},

		// Unicode characters
		{"\U0001F4A9"}, // Emoji
		{"\u2764"},     // Heart

		// Mixed input
		{"Hello, \nWorld!\r\nYours,\t\"GraphQL\""},
		{" # This comment has a \u0A0A multi-byte character."},
		{"\"unicode \\u1234\\u5678\\u90AB\\uCDEF\""},
		{"こんにちは, 世界!\n \U0001F4A9"},
		{"\"Has a фы世界 multi-byte character.\""},

		// invalid, but not failing with escape function. Do not know if ok or not?
		{"\\uD802\\u"},
		{"\\uDBFF\\uFFFF"},
		{"\\u{D800}"},
		{"\\uD800"},
		{"\"bфы世ыы𠱸d \\uXXXF esc\""},
	}

	for _, testCase := range testCases {
		escaped := escapeGraphQLString(testCase.input)
		// escaped := testCase.input
		query := fmt.Sprintf(`{ echo(text: "%s") }`, escaped)
		resp, err := http.Get("http://localhost:8080/graphql?query=" + url.QueryEscape(query))
		if err != nil {
			t.Fatalf("Error sending query: %v", err)
		}
		defer resp.Body.Close()

		body, err := ioutil.ReadAll(resp.Body)
		if err != nil {
			t.Fatalf("Error reading response body: %v", err)
		}

		var result graphqlResponse
		err = json.Unmarshal(body, &result)
		if err != nil {
			t.Fatalf("Error unmarshaling response: %v", err)
		}

		if result.Data.Echo != testCase.input {
			t.Errorf("Expected: %q, got: %q for input: %s", testCase.input, result.Data.Echo, testCase.input)
		}
	}
}

// func TestBinaryFileEscapeGraphQLString(t *testing.T) {
// 	filePath := "/Users/home/.gnupg/trustdb.gpg"
// 	content, err := ioutil.ReadFile(filePath)
// 	if err != nil {
// 		fmt.Println("Error reading file:", err)
// 		return
// 	}

// 	input := string(content)
// 	escaped := escapeGraphQLString(input)
// 	query := fmt.Sprintf(`{ echo(text: "%s") }`, escaped)
// 	resp, err := http.Get("http://localhost:8080/graphql?query=" + url.QueryEscape(query))
// 	if err != nil {
// 		t.Fatalf("Error sending query: %v", err)
// 	}
// 	defer resp.Body.Close()

// 	body, err := ioutil.ReadAll(resp.Body)
// 	if err != nil {
// 		t.Fatalf("Error reading response body: %v", err)
// 	}

// 	var result graphqlResponse
// 	err = json.Unmarshal(body, &result)
// 	if err != nil {
// 		t.Fatalf("Error unmarshaling response: %v", err)
// 	}

// 	if result.Data.Echo != string(content) {
// 		t.Errorf("Expected: %s, got: %s for input: %s", string(content), result.Data.Echo, filePath)
// 	}
// }

func TestBinaryFileEscapeGraphQLString(t *testing.T) {
	filePath := "/Users/home/.gnupg/trustdb.gpg"

	fileData, err := ioutil.ReadFile(filePath)
	if err != nil {
		t.Fatal(err)
	}

	// Call the escapeGraphQLString function.
	escaped := escapeGraphQLString(string(fileData))

	query := fmt.Sprintf(`{ echo(text: "%s") }`, escaped)
	resp, err := http.Get("http://localhost:8080/graphql?query=" + url.QueryEscape(query))
	if err != nil {
		t.Fatalf("Error sending query: %v", err)
	}
	defer resp.Body.Close()

	body, err := ioutil.ReadAll(resp.Body)
	if err != nil {
		t.Fatalf("Error reading response body: %v", err)
	}

	var result graphqlResponse
	err = json.Unmarshal(body, &result)
	if err != nil {
		t.Fatalf("Error unmarshaling response: %v", err)
	}

	// Compare the base64-encoded strings.
	if result.Data.Echo != string(fileData) {
		t.Errorf("Expected: %q, got: %q for input: %s", string(fileData), result.Data.Echo, filePath)
	}
}
