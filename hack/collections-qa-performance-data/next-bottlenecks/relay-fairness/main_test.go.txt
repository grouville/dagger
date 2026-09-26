package main

import (
	"bytes"
	"compress/gzip"
	"context"
	"crypto/sha256"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"net/url"
	"os"
	"path/filepath"
	"sync/atomic"
	"testing"
	"time"

	coltrace "go.opentelemetry.io/proto/otlp/collector/trace/v1"
	"google.golang.org/protobuf/proto"
)

type testTransport func(*http.Request) (*http.Response, error)

type incompleteBody struct{}

func (incompleteBody) Read([]byte) (int, error) { return 0, io.ErrUnexpectedEOF }
func (incompleteBody) Close() error             { return nil }

func (f testTransport) RoundTrip(req *http.Request) (*http.Response, error) { return f(req) }
func makeRelay(t *testing.T, transport testTransport) *relay {
	t.Helper()
	u, _ := url.Parse("https://fake.invalid")
	r, err := openRelay(t.TempDir(), u, &http.Client{Transport: transport})
	if err != nil {
		t.Fatal(err)
	}
	r.admin = sha256.Sum256([]byte("fake-administrative-token"))
	t.Cleanup(r.close)
	return r
}
func response(status int) *http.Response {
	return &http.Response{StatusCode: status, Header: http.Header{"Content-Type": []string{"application/x-protobuf"}}, Body: io.NopCloser(bytes.NewReader(nil))}
}
func enqueueStatus(r *relay, seq string) int {
	req := httptest.NewRequest("POST", "http://relay.invalid/v1/traces?test=value", bytes.NewReader([]byte{1, 2, 3}))
	req.Header.Set("Authorization", "fake-credential")
	req.Header.Set("X-Dagger-Export", seq)
	w := httptest.NewRecorder()
	r.serve(w, req)
	return w.Code
}
func enqueue(t *testing.T, r *relay, seq string) {
	t.Helper()
	if code := enqueueStatus(r, seq); code != 200 {
		t.Fatalf("enqueue status=%d", code)
	}
}
func waitFor(t *testing.T, r *relay, want func(stats) bool) stats {
	t.Helper()
	deadline := time.Now().Add(3 * time.Second)
	for time.Now().Before(deadline) {
		s := r.snapshot()
		if want(s) {
			return s
		}
		time.Sleep(time.Millisecond)
	}
	t.Fatalf("stats deadline: %+v", r.snapshot())
	return stats{}
}
func TestRetryAfterAcrossWorkers(t *testing.T) {
	attempts := make(chan time.Time, 8)
	var calls atomic.Int32
	r := makeRelay(t, func(req *http.Request) (*http.Response, error) {
		if req.Header.Get("X-Dagger-Export") == "writer-a/1" {
			attempts <- time.Now()
			if calls.Add(1) == 1 {
				resp := response(429)
				resp.Header.Set("Retry-After", "1")
				return resp, nil
			}
		}
		return response(200), nil
	})
	enqueue(t, r, "writer-a/1")
	r.start(4)
	first := <-attempts
	enqueue(t, r, "writer-b/1")
	waitFor(t, r, func(s stats) bool { return s.Delivered == 1 })
	select {
	case second := <-attempts:
		if second.Sub(first) < 900*time.Millisecond {
			t.Fatalf("Retry-After bypassed: %v", second.Sub(first))
		}
	case <-time.After(2 * time.Second):
		t.Fatal("retry never scheduled")
	}
	waitFor(t, r, func(s stats) bool { return s.Pending == 0 && s.Delivered == 2 })
}
func TestExclusiveRecoveryAndDurableReplay(t *testing.T) {
	var calls atomic.Int32
	r := makeRelay(t, func(*http.Request) (*http.Response, error) { calls.Add(1); return response(200), nil })
	enqueue(t, r, "writer/1")
	files, _ := filepath.Glob(filepath.Join(r.dir, "*.json"))
	if len(files) != 1 {
		t.Fatal("missing durable record")
	}
	info, err := os.Stat(files[0])
	if err != nil || info.Mode().Perm() != 0600 {
		t.Fatalf("file permissions: %v", err)
	}
	tmp := filepath.Join(r.dir, "abandoned.tmp")
	if err := os.WriteFile(tmp, []byte("fake incomplete record"), 0600); err != nil {
		t.Fatal(err)
	}
	if other, err := openRelay(r.dir, r.target, r.client); err == nil {
		other.close()
		t.Fatal("second owner acquired spool")
	}
	if _, err := os.Stat(tmp); err != nil {
		t.Fatal("second owner touched first owner's temp file")
	}
	r.close()
	recovered, err := openRelay(r.dir, r.target, r.client)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(recovered.close)
	if _, err := os.Stat(tmp); !errors.Is(err, os.ErrNotExist) {
		t.Fatal("abandoned temp not removed")
	}
	if recovered.snapshot().Pending != 1 {
		t.Fatal("record not recovered")
	}
	recovered.start(4)
	waitFor(t, recovered, func(s stats) bool { return s.Pending == 0 && s.Delivered == 1 })
	if calls.Load() != 1 {
		t.Fatal("unexpected delivery count")
	}
}
func TestRenameThenSyncFailureReconcilesRetry(t *testing.T) {
	var network atomic.Int32
	r := makeRelay(t, func(*http.Request) (*http.Response, error) { network.Add(1); return response(200), nil })
	var syncs atomic.Int32
	r.syncDirectory = func(dir string) error {
		if syncs.Add(1) == 1 {
			return errors.New("injected directory sync")
		}
		return syncDir(dir)
	}
	r.start(4)
	if code := enqueueStatus(r, "writer/1"); code != 503 {
		t.Fatalf("uncertain persistence acked %d", code)
	}
	if s := r.snapshot(); s.Pending != 1 || s.Accepted != 0 || s.StorageErrors != 1 {
		t.Fatalf("untracked uncertain rename: %+v", s)
	}
	if network.Load() != 0 {
		t.Fatal("undurable record delivered")
	}
	enqueue(t, r, "writer/1")
	waitFor(t, r, func(s stats) bool { return s.Pending == 0 && s.Delivered == 1 && s.Accepted == 1 })
	if network.Load() != 1 {
		t.Fatal("retry duplicated record")
	}
}

func TestRecoveryCountersIgnoreLaterAcceptedRecords(t *testing.T) {
	r := makeRelay(t, nil)
	enqueue(t, r, "writer/1")
	before := r.snapshot()
	if before.Recovered != 0 || before.RecoveredBytes != 0 {
		t.Fatal("freshly accepted record counted as recovered")
	}
	r.close()
	recovered, err := openRelay(r.dir, r.target, r.client)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(recovered.close)
	checkpoint := recovered.snapshot()
	if checkpoint.Recovered != 1 || checkpoint.RecoveredBytes != before.Bytes {
		t.Fatalf("startup checkpoint differs from spool: %+v", checkpoint)
	}
	enqueue(t, recovered, "writer/2")
	after := recovered.snapshot()
	if after.Recovered != checkpoint.Recovered || after.RecoveredBytes != checkpoint.RecoveredBytes || after.Pending != 2 || after.Bytes <= checkpoint.RecoveredBytes {
		t.Fatalf("post-start acceptance changed recovery checkpoint: %+v", after)
	}
}
func TestUnlinkThenSyncFailureDoesNotRequeueMissingFile(t *testing.T) {
	var network atomic.Int32
	r := makeRelay(t, func(*http.Request) (*http.Response, error) { network.Add(1); return response(200), nil })
	enqueue(t, r, "writer/1")
	r.syncDirectory = func(string) error { return errors.New("injected directory sync") }
	r.start(4)
	s := waitFor(t, r, func(s stats) bool { return s.Pending == 0 && s.Delivered == 1 })
	if s.StorageErrors != 1 || s.Retries != 0 || s.Bytes != 0 || network.Load() != 1 {
		t.Fatalf("incorrect cleanup accounting: %+v", s)
	}
}
func TestUnlinkRetryDoesNotRedeliver(t *testing.T) {
	var network, unlinks atomic.Int32
	r := makeRelay(t, func(*http.Request) (*http.Response, error) { network.Add(1); return response(200), nil })
	enqueue(t, r, "writer/1")
	r.removeFile = func(path string) error {
		if unlinks.Add(1) == 1 {
			return errors.New("injected unlink")
		}
		return os.Remove(path)
	}
	r.start(4)
	waitFor(t, r, func(s stats) bool { return s.Delivered == 1 && s.CleanupPending == 1 })
	waitFor(t, r, func(s stats) bool { return s.Pending == 0 })
	if network.Load() != 1 {
		t.Fatal("cleanup retry repeated network upload")
	}
}
func TestPartialResponseIsDurableTerminalFailure(t *testing.T) {
	body, _ := proto.Marshal(&coltrace.ExportTraceServiceResponse{PartialSuccess: &coltrace.ExportTracePartialSuccess{RejectedSpans: 1}})
	var network atomic.Int32
	r := makeRelay(t, func(req *http.Request) (*http.Response, error) {
		network.Add(1)
		resp := response(200)
		if req.Header.Get("X-Dagger-Export") == "writer-a/1" {
			resp.Body = io.NopCloser(bytes.NewReader(body))
		}
		return resp, nil
	})
	enqueue(t, r, "writer-a/1")
	enqueue(t, r, "writer-a/2")
	enqueue(t, r, "writer-b/1")
	r.start(4)
	waitFor(t, r, func(s stats) bool { return s.Failed == 1 && s.Delivered == 1 })
	r.close()
	if network.Load() != 2 {
		t.Fatal("terminal writer was retried or overtaken")
	}
	recovered, err := openRelay(r.dir, r.target, r.client)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(recovered.close)
	s := recovered.snapshot()
	if s.Failed != 1 || s.Pending != 2 {
		t.Fatalf("terminal evidence not recovered: %+v", s)
	}
	for _, q := range recovered.queues {
		if !q.blocked {
			t.Fatal("failed writer resumed on restart")
		}
	}
}
func TestRejectedRequestIsNotRetried(t *testing.T) {
	for _, status := range []int{400, 401, 403, 500} {
		t.Run(fmt.Sprint(status), func(t *testing.T) {
			var calls atomic.Int32
			r := makeRelay(t, func(*http.Request) (*http.Response, error) { calls.Add(1); return response(status), nil })
			enqueue(t, r, "writer/1")
			r.start(4)
			s := waitFor(t, r, func(s stats) bool { return s.Failed == 1 })
			if s.Retries != 0 || s.Delivered != 0 || calls.Load() != 1 {
				t.Fatalf("rejected record retried: %+v", s)
			}
		})
	}
}

func TestPermanentStatusWinsTruncatedBody(t *testing.T) {
	r := makeRelay(t, func(*http.Request) (*http.Response, error) {
		resp := response(400)
		resp.Body = incompleteBody{}
		return resp, nil
	})
	enqueue(t, r, "writer/1")
	r.start(4)
	s := waitFor(t, r, func(s stats) bool { return s.Failed == 1 })
	if s.Retries != 0 {
		t.Fatal("permanent rejection retried because its error body was truncated")
	}
}
func TestSuccessfulAndCompressedResponses(t *testing.T) {
	for _, path := range []string{"/v1/traces", "/v1/logs", "/v1/metrics"} {
		if !acceptedResponse(path, "application/x-protobuf", nil) {
			t.Fatal("empty protobuf rejected")
		}
		if !acceptedResponse(path, "application/json", []byte("{}")) {
			t.Fatal("JSON success rejected")
		}
	}
	b, _ := proto.Marshal(&coltrace.ExportTraceServiceResponse{PartialSuccess: &coltrace.ExportTracePartialSuccess{ErrorMessage: "warning only"}})
	var compressed bytes.Buffer
	g := gzip.NewWriter(&compressed)
	g.Write(b)
	g.Close()
	resp := response(200)
	resp.Header.Set("Content-Encoding", "gzip")
	resp.Body = io.NopCloser(&compressed)
	decoded, err := readResponse(resp)
	if err != nil || !bytes.Equal(decoded, b) || !acceptedResponse("/v1/traces", "application/x-protobuf", decoded) {
		t.Fatal("valid compressed response rejected")
	}
	if acceptedResponse("/v1/traces", "text/html", []byte("okay")) {
		t.Fatal("invalid content type accepted")
	}
}

func TestInvalidSuccessIsTerminal(t *testing.T) {
	for _, encoding := range []string{"gzip", "br", ""} {
		t.Run(encoding, func(t *testing.T) {
			r := makeRelay(t, func(*http.Request) (*http.Response, error) {
				resp := response(200)
				resp.Header.Set("Content-Encoding", encoding)
				resp.Body = io.NopCloser(bytes.NewBufferString("not a valid encoded OTLP response"))
				return resp, nil
			})
			enqueue(t, r, "writer/1")
			r.start(4)
			s := waitFor(t, r, func(s stats) bool { return s.Failed == 1 })
			if s.Retries != 0 || s.Delivered != 0 {
				t.Fatalf("invalid response was retried or acknowledged: %+v", s)
			}
		})
	}
}
func TestForwardQueryAndAdministrativeIsolation(t *testing.T) {
	var calls atomic.Int32
	r := makeRelay(t, func(req *http.Request) (*http.Response, error) {
		calls.Add(1)
		if req.URL.RawQuery != "a=1&a=2%2F3" {
			t.Errorf("query changed: %q", req.URL.RawQuery)
		}
		if req.Header.Get("X-Relay-Admin") != "" || req.Header.Get("Private-Hop") != "" {
			t.Error("private/hop header forwarded")
		}
		return response(200), nil
	})
	req := httptest.NewRequest("GET", "http://relay.invalid/other?a=1&a=2%2F3", nil)
	req.Header.Set("X-Relay-Admin", "must not forward")
	req.Header.Set("Connection", "Private-Hop")
	req.Header.Set("Private-Hop", "must not forward")
	w := httptest.NewRecorder()
	r.serve(w, req)
	if w.Code != 200 {
		t.Fatal("forward failed")
	}
	for _, path := range []string{"/relay/stats", "/relay/pause", "/relay/resume", "/relay/mode?value=sync"} {
		w := httptest.NewRecorder()
		r.serve(w, httptest.NewRequest("POST", path, nil))
		if w.Code != 403 {
			t.Fatal("admin request accepted without token")
		}
	}
	req = httptest.NewRequest("POST", "/relay/unknown", nil)
	req.Header.Set("X-Relay-Admin", "fake-administrative-token")
	w = httptest.NewRecorder()
	r.serve(w, req)
	if w.Code != 404 || calls.Load() != 1 {
		t.Fatal("unknown admin endpoint escaped to upstream")
	}
}
func TestBoundedTombstones(t *testing.T) {
	r := makeRelay(t, nil)
	for i := range tombstoneLimit + 100 {
		e := &entry{key: fmt.Sprint(i), writer: fmt.Sprint(i), size: 1}
		r.mu.Lock()
		r.addLocked(e)
		q := r.queues[e.writer]
		r.mu.Unlock()
		r.finish(e, q)
	}
	s := r.snapshot()
	if s.Tombstones != tombstoneLimit || len(r.keys) != 0 || len(r.queues) != 0 || len(r.writers) != 0 {
		t.Fatalf("unbounded retained state: %+v", s)
	}
}
func TestCancellationRetainsAcceptedRecords(t *testing.T) {
	started := make(chan struct{})
	r := makeRelay(t, func(req *http.Request) (*http.Response, error) {
		close(started)
		<-req.Context().Done()
		return nil, req.Context().Err()
	})
	enqueue(t, r, "writer/1")
	r.start(1)
	<-started
	r.close()
	files, _ := filepath.Glob(filepath.Join(r.dir, "*.json"))
	if len(files) != 1 || r.snapshot().Pending != 1 {
		t.Fatal("cancellation lost accepted record")
	}
}
func TestDedupKeysHaveUnambiguousFieldBoundaries(t *testing.T) {
	a := record{Path: "/v1/traces", Header: http.Header{"Authorization": []string{"a"}, "X-Dagger-Org": []string{"bc"}}}
	b := a
	b.Header = a.Header.Clone()
	b.Header.Set("Authorization", "ab")
	b.Header.Set("X-Dagger-Org", "c")
	if recordKey(a) == recordKey(b) {
		t.Fatal("ambiguous dedup fields")
	}
}
func TestSpoolCapRejectsBeforePersistence(t *testing.T) {
	r := makeRelay(t, nil)
	r.stats.Bytes = spoolLimit
	if code := enqueueStatus(r, "writer/1"); code != 503 {
		t.Fatal("full spool accepted data")
	}
	if len(r.keys) != 0 {
		t.Fatal("rejected record tracked as accepted")
	}
}
func TestStatsAreSafeMetadata(t *testing.T) {
	r := makeRelay(t, nil)
	enqueue(t, r, "writer/1")
	data, err := json.Marshal(r.snapshot())
	if err != nil {
		t.Fatal(err)
	}
	if bytes.Contains(data, []byte("fake-credential")) {
		t.Fatal("credential in stats")
	}
}
func TestSyncPassthroughUsesRequestCancellation(t *testing.T) {
	r := makeRelay(t, func(req *http.Request) (*http.Response, error) { return nil, req.Context().Err() })
	r.synchronous = true
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	req := httptest.NewRequest("POST", "http://relay.invalid/v1/traces", nil).WithContext(ctx)
	w := httptest.NewRecorder()
	r.serve(w, req)
	if w.Code != 502 || r.snapshot().Pending != 0 {
		t.Fatal("sync cancellation was spooled")
	}
}

func TestExportCountersCoverSynchronousAndAsync(t *testing.T) {
	r := makeRelay(t, func(*http.Request) (*http.Response, error) { return response(200), nil })
	r.synchronous = true
	enqueue(t, r, "writer-sync/1")
	s := r.snapshot()
	if s.ExportRequests != 1 || s.ExportRequestBytes != 3 || s.Export2xx != 1 || s.ExportActive != 0 || s.Accepted != 0 || s.TraceRequests != 1 || s.TraceRequestBytes != 3 {
		t.Fatalf("sync transport not counted: %+v", s)
	}
	r.synchronous = false
	enqueue(t, r, "writer-async/1")
	r.start(4)
	s = waitFor(t, r, func(s stats) bool { return s.Pending == 0 && s.Delivered == 1 })
	if s.ExportRequests != 2 || s.ExportRequestBytes != 6 || s.Export2xx != 2 || s.TraceRequests != 2 || s.ExportActive != 0 || s.QueueStarts != 1 || s.PayloadReadNS <= 0 {
		t.Fatalf("async transport not counted: %+v", s)
	}
}

func TestExportCounterIncludesResponseBodyAndNetworkError(t *testing.T) {
	r := makeRelay(t, func(*http.Request) (*http.Response, error) {
		resp := response(201)
		resp.Body = io.NopCloser(bytes.NewBufferString("response"))
		return resp, nil
	})
	r.synchronous = true
	if enqueueStatus(r, "writer/1") != 201 {
		t.Fatal("upstream response changed")
	}
	s := r.snapshot()
	if s.ExportResponseBytes != 8 || s.Export2xx != 1 || s.ExportDurationNS <= 0 || s.ExportHeaderNS <= 0 {
		t.Fatalf("response missing: %+v", s)
	}
	r.client = &http.Client{Transport: testTransport(func(*http.Request) (*http.Response, error) { return nil, io.ErrUnexpectedEOF })}
	if enqueueStatus(r, "writer/2") != 502 {
		t.Fatal("expected network error")
	}
	s = r.snapshot()
	if s.ExportRequests != 2 || s.ExportErrors != 1 || s.ExportActive != 0 {
		t.Fatalf("network error missing: %+v", s)
	}
}
