package dangshared

import (
	"context"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/Khan/genqlient/graphql"
)

// This is a screening model, not a transport proposed for production. Keeping
// genqlient and the HTTP handler bounds the work removable from the TCP path.
type benchmarkHandlerTransport struct{ handler http.Handler }

func (t benchmarkHandlerTransport) RoundTrip(req *http.Request) (*http.Response, error) {
	defer req.Body.Close()
	response := httptest.NewRecorder()
	t.handler.ServeHTTP(response, req)
	return response.Result(), nil
}

func BenchmarkNestedGraphQLTransport(b *testing.B) {
	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if _, err := io.Copy(io.Discard, r.Body); err != nil {
			panic(err)
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = io.WriteString(w, `{"data":{"currentWorkspace":{"id":"Workspace@XXH3:0123456789abcdef"}}}`)
	})
	for _, transport := range []string{"tcp", "handler"} {
		for _, requests := range []int{0, 2, 8} {
			b.Run(fmt.Sprintf("%s/%d", transport, requests), func(b *testing.B) {
				b.ReportAllocs()
				for b.Loop() {
					call := func(ctx context.Context, client graphql.Client) ([]byte, error) {
						for range requests {
							var result struct {
								Workspace struct {
									ID string `json:"id"`
								} `json:"currentWorkspace"`
							}
							err := client.MakeRequest(ctx, &graphql.Request{Query: "query { currentWorkspace { id } }"}, &graphql.Response{Data: &result})
							if err != nil {
								return nil, err
							}
							if result.Workspace.ID != "Workspace@XXH3:0123456789abcdef" {
								return nil, fmt.Errorf("incorrect workspace ID: %q", result.Workspace.ID)
							}
						}
						return nil, nil
					}
					var err error
					if transport == "tcp" {
						_, err = serveNestedClient(b.Context(), &http.Server{Handler: handler}, http.DefaultTransport.(*http.Transport).Clone(), call)
					} else {
						client := graphql.NewClient("http://nested-client/query", &http.Client{Transport: benchmarkHandlerTransport{handler}})
						_, err = call(b.Context(), client)
					}
					if err != nil {
						b.Fatal(err)
					}
				}
			})
		}
	}
}
