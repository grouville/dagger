package core

import (
	"context"
	"fmt"
	"net"
	"net/http"
	"os"
	"strings"

	"dagger.io/dagger"
	"github.com/dagger/testctx"
	"github.com/stretchr/testify/require"
)

const localURLTestModel = "local-url-test-model"

func localURLTestOpenAIStream(reply string) string {
	return fmt.Sprintf("data: "+`{"id":"chatcmpl-review","object":"chat.completion.chunk","created":1,"model":%q,"choices":[{"index":0,"delta":{"role":"assistant","content":%q},"finish_reason":null}]}`+"\n\n"+
		"data: "+`{"id":"chatcmpl-review","object":"chat.completion.chunk","created":1,"model":%q,"choices":[{"index":0,"delta":{},"finish_reason":"stop"}],"usage":{"prompt_tokens":1,"completion_tokens":1,"total_tokens":2}}`+"\n\n"+
		"data: [DONE]\n\n", localURLTestModel, reply, localURLTestModel)
}

func (LLMSuite) TestNestedSameLocalURLUsesNestedClient(ctx context.Context, t *testctx.T) {
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	require.NoError(t, err)
	port := listener.Addr().(*net.TCPAddr).Port
	outerServer := &http.Server{Handler: http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "text/event-stream")
		fmt.Fprint(w, localURLTestOpenAIStream("OUTER"))
	})}
	go outerServer.Serve(listener)
	t.Cleanup(func() { outerServer.Close() })

	baseURL := fmt.Sprintf("http://127.0.0.1:%d", port)
	for key, value := range map[string]string{
		"LOCAL_BASE_URL":   baseURL,
		"LOCAL_MODEL":      localURLTestModel,
		"LOCAL_API_COMPAT": "openai",
	} {
		old, present := os.LookupEnv(key)
		require.NoError(t, os.Setenv(key, value))
		t.Cleanup(func() {
			if present {
				_ = os.Setenv(key, old)
			} else {
				_ = os.Unsetenv(key)
			}
		})
	}

	nestedServerSource := fmt.Sprintf(`package main
import ("fmt"; "net"; "net/http"; "os")
func main() {
  ln, err := net.Listen("tcp", "127.0.0.1:%d"); if err != nil { panic(err) }
  if err := os.WriteFile("/tmp/review-server-ready", []byte("ready"), 0600); err != nil { panic(err) }
  http.Serve(ln, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
    w.Header().Set("Content-Type", "text/event-stream")
    fmt.Fprint(w, %q)
  }))
}`, port, localURLTestOpenAIStream("NESTED"))

	c := connect(ctx, t)
	ctr := goGitBase(t, c).
		WithNewFile("/tmp/review-server.go", nestedServerSource).
		WithEnvVariable("LOCAL_BASE_URL", baseURL).
		WithEnvVariable("LOCAL_MODEL", localURLTestModel).
		WithEnvVariable("LOCAL_API_COMPAT", "openai")
	command := strings.Join([]string{
		"go run /tmp/review-server.go >/tmp/review-server.log 2>&1 &",
		"for i in $(seq 1 200); do [ -f /tmp/review-server-ready ] && break; sleep 0.05; done",
		"[ -f /tmp/review-server-ready ]",
		"dagger core llm --model " + localURLTestModel + " with-prompt --prompt hello loop last-reply",
	}, "\n")
	out, err := ctr.WithExec([]string{"sh", "-c", command}, dagger.ContainerWithExecOpts{
		ExperimentalPrivilegedNesting: true,
	}).Stdout(ctx)
	require.NoError(t, err)
	require.Equal(t, "NESTED", strings.TrimSpace(out),
		"nested LLM request should reach the nested client's localhost")
}
