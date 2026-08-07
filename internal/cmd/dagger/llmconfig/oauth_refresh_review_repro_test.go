package llmconfig

import (
	"io"
	"net/http"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/stretchr/testify/require"
)

type oauthTestRoundTripFunc func(*http.Request) (*http.Response, error)

func (fn oauthTestRoundTripFunc) RoundTrip(req *http.Request) (*http.Response, error) {
	return fn(req)
}

func TestRefreshOAuthProviderIfNeededConcurrent(t *testing.T) {
	oldRoot, oldFile := ConfigRoot, ConfigFile
	ConfigRoot = t.TempDir()
	ConfigFile = ConfigRoot + "/config.toml"
	t.Cleanup(func() {
		ConfigRoot, ConfigFile = oldRoot, oldFile
	})

	cfg := &Config{LLM: LLMConfig{Providers: map[string]Provider{
		"anthropic": {
			AuthType:     "oauth",
			AuthToken:    "expired-access-token",
			RefreshToken: "rotating-refresh-token",
			TokenExpiry:  time.Now().Add(-time.Hour).UnixMilli(),
			Enabled:      true,
		},
	}}}
	require.NoError(t, cfg.Save())

	oldTransport := http.DefaultTransport
	t.Cleanup(func() { http.DefaultTransport = oldTransport })
	var mu sync.Mutex
	refreshRequests := 0
	releaseRefresh := make(chan struct{})
	var releaseOnce sync.Once
	http.DefaultTransport = oauthTestRoundTripFunc(func(req *http.Request) (*http.Response, error) {
		if req.Method != http.MethodPost {
			return &http.Response{
				StatusCode: http.StatusInternalServerError,
				Body:       io.NopCloser(strings.NewReader("profile lookup disabled")),
				Header:     make(http.Header),
				Request:    req,
			}, nil
		}
		mu.Lock()
		refreshRequests++
		n := refreshRequests
		if refreshRequests == 2 {
			releaseOnce.Do(func() { close(releaseRefresh) })
		}
		mu.Unlock()
		if n == 1 {
			select {
			case <-releaseRefresh:
			case <-time.After(250 * time.Millisecond):
				releaseOnce.Do(func() { close(releaseRefresh) })
			}
		} else {
			<-releaseRefresh
		}
		if n == 2 {
			return &http.Response{
				StatusCode: http.StatusBadRequest,
				Body:       io.NopCloser(strings.NewReader(`{"error":"invalid_grant","error_description":"refresh token already used"}`)),
				Header:     make(http.Header),
				Request:    req,
			}, nil
		}
		return &http.Response{
			StatusCode: http.StatusOK,
			Body: io.NopCloser(strings.NewReader(
				`{"access_token":"new-access-token","refresh_token":"new-refresh-token","expires_in":3600}`)),
			Header:  make(http.Header),
			Request: req,
		}, nil
	})

	errs := make(chan error, 2)
	var wg sync.WaitGroup
	for range 2 {
		wg.Add(1)
		go func() {
			defer wg.Done()
			_, err := RefreshOAuthProviderIfNeeded("anthropic")
			errs <- err
		}()
	}
	wg.Wait()
	close(errs)

	for err := range errs {
		require.NoError(t, err,
			"serialized refreshes should let both callers reuse one successful rotation")
	}
	require.Equal(t, 1, refreshRequests, "a rotating refresh token must only be submitted once")
}
