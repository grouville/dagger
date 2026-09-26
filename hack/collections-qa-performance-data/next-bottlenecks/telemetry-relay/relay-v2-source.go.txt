// Experimental Linux-only durable local OTLP relay. Spool files contain
// credentials: keep the directory private and never archive or log its contents.
package main

import (
	"bytes"
	"compress/gzip"
	"context"
	"crypto/sha256"
	"crypto/subtle"
	"crypto/tls"
	"encoding/binary"
	"encoding/hex"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"mime"
	"net/http"
	"net/http/httptrace"
	"net/url"
	"os"
	"os/signal"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"syscall"
	"time"

	collogs "go.opentelemetry.io/proto/otlp/collector/logs/v1"
	colmetrics "go.opentelemetry.io/proto/otlp/collector/metrics/v1"
	coltrace "go.opentelemetry.io/proto/otlp/collector/trace/v1"
	"google.golang.org/protobuf/encoding/protojson"
	"google.golang.org/protobuf/proto"
)

const spoolLimit = 128 << 20
const tombstoneLimit = 4096

var errInvalidResponse = errors.New("invalid response encoding")

type record struct {
	Path, Query string
	Header      http.Header
	Body        []byte
	Key         string
	Enqueued    int64
}
type stats struct {
	Accepted, Delivered, Retries, Pending, Bytes                                                       int64
	Failed, StorageErrors, CleanupPending, Tombstones                                                  int64
	Recovered, RecoveredBytes                                                                          int64
	LastStatus                                                                                         int
	PersistNS, DeliverNS, OldestPendingNS                                                              int64
	ExportRequests, ExportRequestBytes, ExportResponseBytes                                            int64
	Export2xx, Export4xx, Export5xx, ExportOther, ExportErrors                                         int64
	ExportDurationNS, ExportHeaderNS, ExportGetConnNS, ExportConnectNS, ExportTLSNS                    int64
	ExportReused, ExportActive, ExportPeak                                                             int64
	TraceRequests, TraceRequestBytes, LogRequests, LogRequestBytes, MetricRequests, MetricRequestBytes int64
	QueueStarts, QueueWaitNS, PayloadReadNS                                                            int64
}
type entry struct {
	name, key, writer          string
	size                       int64
	enqueued                   int64
	durable, remoteAck, failed bool
}
type writerQueue struct {
	entries         []*entry
	active, blocked bool
	next            time.Time
	attempts        int
}
type relay struct {
	admin                     [32]byte
	dir                       string
	target                    *url.URL
	client                    *http.Client
	spoolLock                 *os.File
	ctx                       context.Context
	cancel                    context.CancelFunc
	wg                        sync.WaitGroup
	closeOnce                 sync.Once
	acceptMu                  sync.Mutex // serialize durable acceptance, separately from scheduling
	mu                        sync.Mutex
	cond                      *sync.Cond
	queues                    map[string]*writerQueue
	writers                   []string
	keys                      map[string]*entry
	recent                    map[string]bool
	recentOrder               []string
	recentNext                int
	lastEnqueued              int64
	stats                     stats
	synchronous, paused, halt bool
	// Fault injection in fake-transport tests, never configured by the daemon.
	syncDirectory func(string) error
	removeFile    func(string) error
}

func openRelay(dir string, target *url.URL, client *http.Client) (*relay, error) {
	if err := os.MkdirAll(dir, 0700); err != nil {
		return nil, err
	}
	if err := os.Chmod(dir, 0700); err != nil {
		return nil, err
	}
	lock, err := os.OpenFile(filepath.Join(dir, ".lock"), os.O_CREATE|os.O_RDWR, 0600)
	if err != nil {
		return nil, err
	}
	if err = syscall.Flock(int(lock.Fd()), syscall.LOCK_EX|syscall.LOCK_NB); err != nil {
		lock.Close()
		return nil, fmt.Errorf("spool is already owned")
	}
	ctx, cancel := context.WithCancel(context.Background())
	r := &relay{dir: dir, target: target, client: client, spoolLock: lock, ctx: ctx, cancel: cancel, queues: map[string]*writerQueue{}, keys: map[string]*entry{}, recent: map[string]bool{}, syncDirectory: syncDir, removeFile: os.Remove}
	r.cond = sync.NewCond(&r.mu)
	if err := r.recover(); err != nil {
		r.close()
		return nil, err
	}
	return r, nil
}
func (r *relay) recover() error {
	// Exclusive spool ownership is established before abandoned writes are removed.
	temps, err := filepath.Glob(filepath.Join(r.dir, "*.tmp"))
	if err != nil {
		return err
	}
	for _, p := range temps {
		if err := os.Remove(p); err != nil {
			return fmt.Errorf("remove abandoned spool write: %w", err)
		}
	}
	if err := r.syncDirectory(r.dir); err != nil {
		return fmt.Errorf("recover spool directory: %w", err)
	}
	paths, err := filepath.Glob(filepath.Join(r.dir, "*.json"))
	if err != nil {
		return err
	}
	sort.Strings(paths)
	for _, p := range paths {
		data, err := os.ReadFile(p)
		if err != nil {
			return fmt.Errorf("unreadable spool record")
		}
		var rec record
		if json.Unmarshal(data, &rec) != nil || len(rec.Key) != 64 || filepath.Base(p) != fmt.Sprintf("%020d-%s.json", rec.Enqueued, rec.Key) {
			return fmt.Errorf("invalid spool record")
		}
		if _, err := hex.DecodeString(rec.Key); err != nil {
			return fmt.Errorf("invalid spool record key")
		}
		e := &entry{name: p, key: rec.Key, writer: writer(rec), size: int64(len(data)), enqueued: rec.Enqueued, durable: true}
		if _, err := os.Stat(r.failurePath(e)); err == nil {
			e.failed = true
		} else if !errors.Is(err, os.ErrNotExist) {
			return fmt.Errorf("unreadable failure marker")
		}
		if _, ok := r.keys[e.key]; ok {
			return fmt.Errorf("duplicate spool record")
		}
		r.addLocked(e)
		r.lastEnqueued = max(r.lastEnqueued, rec.Enqueued)
		r.stats.Accepted++
		if e.failed {
			r.stats.Failed++
			r.queues[e.writer].blocked = true
		}
	}
	// Immutable startup checkpoint: new requests can arrive after ListenAndServe
	// begins, even when outbound delivery is paused.
	r.stats.Recovered = r.stats.Pending
	r.stats.RecoveredBytes = r.stats.Bytes
	return nil
}
func (r *relay) start(n int) {
	for range n {
		r.wg.Add(1)
		go func() { defer r.wg.Done(); r.work() }()
	}
}
func (r *relay) close() {
	r.closeOnce.Do(func() {
		r.acceptMu.Lock()
		r.mu.Lock()
		r.halt = true
		r.cond.Broadcast()
		r.mu.Unlock()
		r.acceptMu.Unlock()
		r.cancel()
		r.wg.Wait()
		syscall.Flock(int(r.spoolLock.Fd()), syscall.LOCK_UN)
		r.spoolLock.Close()
	})
}
func (r *relay) addLocked(e *entry) {
	q := r.queues[e.writer]
	if q == nil {
		q = &writerQueue{}
		r.queues[e.writer] = q
		r.writers = append(r.writers, e.writer)
	}
	q.entries = append(q.entries, e)
	r.keys[e.key] = e
	r.stats.Bytes += e.size
	r.stats.Pending++
}
func (r *relay) snapshot() stats {
	r.mu.Lock()
	defer r.mu.Unlock()
	s := r.stats
	s.Tombstones = int64(len(r.recent))
	now := time.Now().UnixNano()
	for _, e := range r.keys {
		if age := now - e.enqueued; age > s.OldestPendingNS {
			s.OldestPendingNS = age
		}
		if e.remoteAck {
			s.CleanupPending++
		}
	}
	return s
}
func (r *relay) ack(w http.ResponseWriter) {
	w.Header().Set("Content-Type", "application/x-protobuf")
	w.WriteHeader(200)
}
func (r *relay) serve(w http.ResponseWriter, req *http.Request) {
	if strings.HasPrefix(req.URL.Path, "/relay/") {
		r.adminServe(w, req)
		return
	}
	if req.Method == "HEAD" && req.URL.Path == "/v1/traces" {
		w.WriteHeader(200)
		return
	}
	body, err := io.ReadAll(io.LimitReader(req.Body, (16<<20)+1))
	if err != nil || len(body) > 16<<20 {
		http.Error(w, "body limit", 413)
		return
	}
	otlp := req.Method == "POST" && (req.URL.Path == "/v1/traces" || req.URL.Path == "/v1/logs" || req.URL.Path == "/v1/metrics")
	r.mu.Lock()
	synchronous := r.synchronous
	r.mu.Unlock()
	if !otlp || synchronous {
		r.forward(w, req, body)
		return
	}
	if req.Header.Get("Authorization") == "" {
		http.Error(w, "authentication required", 401)
		return
	}
	rec := record{Path: req.URL.Path, Query: req.URL.RawQuery, Header: req.Header.Clone(), Body: body}
	rec.Header.Del("X-Relay-Admin")
	rec.Key = recordKey(rec)
	start := time.Now()
	r.acceptMu.Lock()
	defer r.acceptMu.Unlock()
	r.mu.Lock()
	if r.halt {
		r.mu.Unlock()
		http.Error(w, "relay stopping", 503)
		return
	}
	if r.recent[rec.Key] {
		r.mu.Unlock()
		r.ack(w)
		return
	}
	if existing := r.keys[rec.Key]; existing != nil {
		durable := existing.durable
		r.mu.Unlock()
		if !durable {
			if err := r.syncDirectory(r.dir); err != nil {
				r.storageError()
				http.Error(w, "spool persistence", 503)
				return
			}
			r.mu.Lock()
			existing.durable = true
			r.stats.Accepted++
			r.cond.Broadcast()
			r.mu.Unlock()
		}
		r.ack(w)
		return
	}
	// Timestamp follows acceptance order, including when requests arrived concurrently.
	rec.Enqueued = max(time.Now().UnixNano(), r.lastEnqueued+1)
	r.lastEnqueued = rec.Enqueued
	r.mu.Unlock()
	encoded, err := json.Marshal(rec)
	if err != nil {
		http.Error(w, "encoding", 500)
		return
	}
	r.mu.Lock()
	if r.stats.Bytes+int64(len(encoded)) > spoolLimit {
		r.mu.Unlock()
		http.Error(w, "spool full", 503)
		return
	}
	r.mu.Unlock()
	name := filepath.Join(r.dir, fmt.Sprintf("%020d-%s.json", rec.Enqueued, rec.Key))
	renamed, err := r.persist(name, encoded)
	if renamed {
		e := &entry{name: name, key: rec.Key, writer: writer(rec), size: int64(len(encoded)), enqueued: rec.Enqueued, durable: err == nil}
		r.mu.Lock()
		r.addLocked(e)
		if err == nil {
			r.stats.Accepted++
		}
		r.stats.PersistNS += time.Since(start).Nanoseconds()
		r.cond.Broadcast()
		r.mu.Unlock()
	}
	if err != nil {
		r.storageError()
		http.Error(w, "spool persistence", 503)
		return
	}
	r.ack(w)
}
func (r *relay) adminServe(w http.ResponseWriter, req *http.Request) {
	key := sha256.Sum256([]byte(req.Header.Get("X-Relay-Admin")))
	if subtle.ConstantTimeCompare(key[:], r.admin[:]) != 1 {
		http.Error(w, "forbidden", 403)
		return
	}
	if req.URL.Path == "/relay/stats" && req.Method == "GET" {
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(r.snapshot())
		return
	}
	if req.Method != "POST" {
		http.Error(w, "method", 405)
		return
	}
	r.mu.Lock()
	defer r.mu.Unlock()
	switch req.URL.Path {
	case "/relay/mode":
		mode := req.URL.Query().Get("value")
		if mode != "sync" && mode != "async" {
			http.Error(w, "mode", 400)
			return
		}
		if r.stats.Pending != 0 {
			http.Error(w, "drain pending records before changing mode", 409)
			return
		}
		r.synchronous = mode == "sync"
	case "/relay/pause":
		r.paused = true
	case "/relay/resume":
		r.paused = false
		r.cond.Broadcast()
	default:
		http.Error(w, "unknown administration endpoint", 404)
		return
	}
	r.ack(w)
}
func recordKey(rec record) string {
	h := sha256.New()
	var n [8]byte
	for _, s := range []string{rec.Header.Get("Authorization"), rec.Header.Get("X-Dagger-Org"), rec.Path, rec.Query, rec.Header.Get("X-Dagger-Export"), rec.Header.Get("Content-Type"), rec.Header.Get("Content-Encoding")} {
		binary.BigEndian.PutUint64(n[:], uint64(len(s)))
		h.Write(n[:])
		io.WriteString(h, s)
	}
	h.Write(rec.Body)
	return hex.EncodeToString(h.Sum(nil))
}
func writer(rec record) string {
	s := rec.Header.Get("X-Dagger-Export")
	if i := strings.LastIndexByte(s, '/'); i > 0 {
		return rec.Header.Get("X-Dagger-Org") + "\x00" + s[:i]
	}
	return rec.Key
}
func syncDir(dir string) error {
	f, e := os.Open(dir)
	if e != nil {
		return e
	}
	defer f.Close()
	return f.Sync()
}

// A renamed file remains indexed even if the directory sync fails. It cannot
// be delivered or acknowledged until a retry confirms the directory sync.
func (r *relay) persist(name string, data []byte) (bool, error) {
	f, err := os.OpenFile(name+".tmp", os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0600)
	if err != nil {
		return false, err
	}
	defer os.Remove(f.Name())
	_, err = f.Write(data)
	if err == nil {
		err = f.Sync()
	}
	closeErr := f.Close()
	if err == nil {
		err = closeErr
	}
	if err != nil {
		return false, err
	}
	if err = os.Rename(f.Name(), name); err != nil {
		return false, err
	}
	return true, r.syncDirectory(r.dir)
}
func (r *relay) storageError() { r.mu.Lock(); r.stats.StorageErrors++; r.mu.Unlock() }
func stripHopHeaders(h http.Header) {
	for _, value := range h.Values("Connection") {
		for _, name := range strings.Split(value, ",") {
			h.Del(strings.TrimSpace(name))
		}
	}
	for _, k := range []string{"Connection", "Keep-Alive", "Proxy-Authenticate", "Proxy-Authorization", "TE", "Trailer", "Transfer-Encoding", "Upgrade", "Content-Length", "X-Relay-Admin"} {
		h.Del(k)
	}
}
func (r *relay) request(ctx context.Context, method, path, query string, header http.Header, body []byte) (*http.Response, error) {
	u := *r.target
	u.Path = strings.TrimSuffix(u.Path, "/") + path
	u.RawPath = ""
	u.RawQuery = query
	req, e := http.NewRequestWithContext(ctx, method, u.String(), bytes.NewReader(body))
	if e != nil {
		return nil, e
	}
	req.Header = header.Clone()
	stripHopHeaders(req.Header)
	if method != "POST" || (path != "/v1/traces" && path != "/v1/logs" && path != "/v1/metrics") {
		return r.client.Do(req)
	}
	return r.exportRequest(req, path, len(body))
}

// Count transport work in both synchronous forwarding and asynchronous replay.
// Payloads/headers/URLs are never recorded; counters include retries.
func (r *relay) exportRequest(req *http.Request, path string, bodyBytes int) (*http.Response, error) {
	start := time.Now()
	var getConnNS, connectNS, tlsNS atomic.Int64
	var reused atomic.Int64
	trace := &httptrace.ClientTrace{
		GetConn: func(string) { getConnNS.Add(-time.Since(start).Nanoseconds()) },
		GotConn: func(info httptrace.GotConnInfo) {
			getConnNS.Add(time.Since(start).Nanoseconds())
			if info.Reused {
				reused.Add(1)
			}
		},
		ConnectStart:      func(string, string) { connectNS.Add(-time.Since(start).Nanoseconds()) },
		ConnectDone:       func(string, string, error) { connectNS.Add(time.Since(start).Nanoseconds()) },
		TLSHandshakeStart: func() { tlsNS.Add(-time.Since(start).Nanoseconds()) },
		TLSHandshakeDone:  func(tls.ConnectionState, error) { tlsNS.Add(time.Since(start).Nanoseconds()) },
	}
	req = req.WithContext(httptrace.WithClientTrace(req.Context(), trace))
	r.mu.Lock()
	r.stats.ExportRequests++
	r.stats.ExportRequestBytes += int64(bodyBytes)
	r.stats.ExportActive++
	r.stats.ExportPeak = max(r.stats.ExportPeak, r.stats.ExportActive)
	switch path {
	case "/v1/traces":
		r.stats.TraceRequests++
		r.stats.TraceRequestBytes += int64(bodyBytes)
	case "/v1/logs":
		r.stats.LogRequests++
		r.stats.LogRequestBytes += int64(bodyBytes)
	case "/v1/metrics":
		r.stats.MetricRequests++
		r.stats.MetricRequestBytes += int64(bodyBytes)
	}
	r.mu.Unlock()
	resp, err := r.client.Do(req)
	headersNS := time.Since(start).Nanoseconds()
	var once sync.Once
	finish := func(n int64, bodyErr error) {
		once.Do(func() {
			r.mu.Lock()
			defer r.mu.Unlock()
			r.stats.ExportActive--
			r.stats.ExportDurationNS += time.Since(start).Nanoseconds()
			r.stats.ExportHeaderNS += headersNS
			r.stats.ExportGetConnNS += max(int64(0), getConnNS.Load())
			r.stats.ExportConnectNS += max(int64(0), connectNS.Load())
			r.stats.ExportTLSNS += max(int64(0), tlsNS.Load())
			r.stats.ExportReused += reused.Load()
			r.stats.ExportResponseBytes += n
			if err != nil || bodyErr != nil {
				r.stats.ExportErrors++
			}
			if resp != nil {
				switch {
				case resp.StatusCode >= 200 && resp.StatusCode < 300:
					r.stats.Export2xx++
				case resp.StatusCode >= 400 && resp.StatusCode < 500:
					r.stats.Export4xx++
				case resp.StatusCode >= 500 && resp.StatusCode < 600:
					r.stats.Export5xx++
				default:
					r.stats.ExportOther++
				}
			}
		})
	}
	if err != nil {
		finish(0, nil)
		return resp, err
	}
	resp.Body = &countedBody{ReadCloser: resp.Body, finish: finish}
	return resp, nil
}

type countedBody struct {
	io.ReadCloser
	n      atomic.Int64
	errMu  sync.Mutex
	err    error
	finish func(int64, error)
}

func (b *countedBody) Read(p []byte) (int, error) {
	n, err := b.ReadCloser.Read(p)
	b.n.Add(int64(n))
	if err != nil && err != io.EOF {
		b.errMu.Lock()
		b.err = err
		b.errMu.Unlock()
	}
	return n, err
}
func (b *countedBody) Close() error {
	err := b.ReadCloser.Close()
	b.errMu.Lock()
	bodyErr := errors.Join(b.err, err)
	b.errMu.Unlock()
	b.finish(b.n.Load(), bodyErr)
	return err
}
func (r *relay) forward(w http.ResponseWriter, req *http.Request, body []byte) {
	resp, e := r.request(req.Context(), req.Method, req.URL.Path, req.URL.RawQuery, req.Header, body)
	if e != nil {
		http.Error(w, "upstream unavailable", 502)
		return
	}
	defer resp.Body.Close()
	h := resp.Header.Clone()
	stripHopHeaders(h)
	for k, v := range h {
		w.Header()[k] = v
	}
	w.WriteHeader(resp.StatusCode)
	io.Copy(w, resp.Body)
}
func (r *relay) next() (*entry, *writerQueue) {
	r.mu.Lock()
	defer r.mu.Unlock()
	for !r.halt {
		var wake time.Time
		if !r.paused {
			for _, id := range r.writers {
				q := r.queues[id]
				if q.active || q.blocked || len(q.entries) == 0 || !q.entries[0].durable {
					continue
				}
				if time.Now().Before(q.next) {
					if wake.IsZero() || q.next.Before(wake) {
						wake = q.next
					}
					continue
				}
				q.active = true
				r.stats.QueueStarts++
				r.stats.QueueWaitNS += max(int64(0), time.Now().UnixNano()-q.entries[0].enqueued)
				return q.entries[0], q
			}
		}
		var timer *time.Timer
		if !wake.IsZero() {
			timer = time.AfterFunc(time.Until(wake), func() { r.mu.Lock(); r.cond.Broadcast(); r.mu.Unlock() })
		}
		r.cond.Wait()
		if timer != nil {
			timer.Stop()
		}
	}
	return nil, nil
}
func (r *relay) finish(e *entry, q *writerQueue) {
	r.mu.Lock()
	defer r.mu.Unlock()
	q.entries = q.entries[1:]
	q.active = false
	q.attempts = 0
	q.next = time.Time{}
	delete(r.keys, e.key)
	r.stats.Pending--
	r.stats.Bytes -= e.size
	if len(r.recentOrder) < tombstoneLimit {
		r.recentOrder = append(r.recentOrder, e.key)
	} else {
		delete(r.recent, r.recentOrder[r.recentNext])
		r.recentOrder[r.recentNext] = e.key
		r.recentNext = (r.recentNext + 1) % tombstoneLimit
	}
	r.recent[e.key] = true
	if len(q.entries) == 0 {
		delete(r.queues, e.writer)
		for i, id := range r.writers {
			if id == e.writer {
				r.writers = append(r.writers[:i], r.writers[i+1:]...)
				break
			}
		}
	}
	r.cond.Broadcast()
}
func (r *relay) retry(q *writerQueue, delay time.Duration) {
	r.mu.Lock()
	defer r.mu.Unlock()
	q.active = false
	q.attempts++
	q.next = time.Now().Add(delay)
	r.stats.Retries++
	r.cond.Broadcast()
}
func (r *relay) failurePath(e *entry) string { return filepath.Join(r.dir, e.key+".failed") }
func (r *relay) terminal(e *entry, q *writerQueue, code string, status int) {
	// No response payload, path, or credential is copied into diagnostics.
	marker, _ := json.Marshal(struct {
		Code   string
		Status int
	}{code, status})
	_, err := r.persist(r.failurePath(e), marker)
	r.mu.Lock()
	defer r.mu.Unlock()
	if err != nil {
		r.stats.StorageErrors++
	}
	e.failed = true
	q.active = false
	q.blocked = true
	r.stats.Failed++
	r.cond.Broadcast()
}
func retryable(status int) bool {
	return status == 429 || status == 502 || status == 503 || status == 504
}
func retryAfter(header string, attempt int) time.Duration {
	if n, err := strconv.ParseInt(header, 10, 64); err == nil && n > 0 && n < 1<<33 {
		return time.Duration(n) * time.Second
	}
	if when, err := http.ParseTime(header); err == nil && time.Until(when) > 0 {
		return time.Until(when)
	}
	return time.Second * time.Duration(1<<min(attempt, 5))
}
func (r *relay) work() {
	for {
		e, q := r.next()
		if e == nil {
			return
		}
		// The selected queue head stays reserved while payload I/O and delivery run.
		if !e.remoteAck {
			readStart := time.Now()
			data, err := os.ReadFile(e.name)
			var rec record
			if err == nil {
				err = json.Unmarshal(data, &rec)
			}
			r.mu.Lock()
			r.stats.PayloadReadNS += time.Since(readStart).Nanoseconds()
			r.mu.Unlock()
			if err != nil {
				r.terminal(e, q, "unreadable-record", 0)
				continue
			}
			start := time.Now()
			ctx, cancel := context.WithTimeout(r.ctx, 15*time.Second)
			resp, requestErr := r.request(ctx, "POST", rec.Path, rec.Query, rec.Header, rec.Body)
			status := 0
			delay := retryAfter("", q.attempts)
			ok := false
			var responseErr error
			if requestErr == nil {
				status = resp.StatusCode
				delay = retryAfter(resp.Header.Get("Retry-After"), q.attempts)
				var response []byte
				response, responseErr = readResponse(resp)
				if responseErr == nil {
					ok = acceptedResponse(rec.Path, resp.Header.Get("Content-Type"), response)
				}
				resp.Body.Close()
			}
			cancel()
			r.mu.Lock()
			r.stats.LastStatus = status
			r.stats.DeliverNS += time.Since(start).Nanoseconds()
			r.mu.Unlock()
			if requestErr != nil || retryable(status) {
				r.retry(q, delay)
				continue
			}
			if status < 200 || status >= 300 {
				r.terminal(e, q, "upstream-rejection", status)
				continue
			}
			if responseErr != nil && !errors.Is(responseErr, errInvalidResponse) {
				r.retry(q, delay)
				continue
			}
			if !ok {
				r.terminal(e, q, "partial-or-invalid-success", status)
				continue
			}
			r.mu.Lock()
			e.remoteAck = true
			r.stats.Delivered++
			r.mu.Unlock()
		}
		if err := r.removeFile(e.name); err != nil && !errors.Is(err, os.ErrNotExist) {
			r.storageError()
			r.retry(q, time.Second)
			continue
		}
		// Once unlinked, never requeue a missing file after a failed directory sync.
		if err := r.syncDirectory(r.dir); err != nil {
			r.storageError()
		}
		r.finish(e, q)
	}
}
func readResponse(resp *http.Response) ([]byte, error) {
	var reader io.Reader = resp.Body
	encoding := strings.ToLower(strings.TrimSpace(resp.Header.Get("Content-Encoding")))
	if encoding != "" && encoding != "identity" && encoding != "gzip" && !resp.Uncompressed {
		return nil, errInvalidResponse
	}
	if encoding == "gzip" && !resp.Uncompressed {
		g, err := gzip.NewReader(reader)
		if err != nil {
			if errors.Is(err, gzip.ErrHeader) {
				return nil, errInvalidResponse
			}
			return nil, err
		}
		defer g.Close()
		reader = g
	}
	b, err := io.ReadAll(io.LimitReader(reader, (1<<20)+1))
	if err == nil && len(b) > 1<<20 {
		err = errInvalidResponse
	}
	if errors.Is(err, gzip.ErrChecksum) {
		err = errInvalidResponse
	}
	return b, err
}
func acceptedResponse(path, contentType string, b []byte) bool {
	if len(b) == 0 {
		return true
	}
	var response proto.Message
	switch path {
	case "/v1/traces":
		response = &coltrace.ExportTraceServiceResponse{}
	case "/v1/logs":
		response = &collogs.ExportLogsServiceResponse{}
	case "/v1/metrics":
		response = &colmetrics.ExportMetricsServiceResponse{}
	default:
		return false
	}
	media, _, err := mime.ParseMediaType(contentType)
	if err != nil && contentType != "" {
		return false
	}
	if media == "application/json" {
		err = protojson.Unmarshal(b, response)
	} else if media == "application/x-protobuf" || media == "" {
		err = proto.Unmarshal(b, response)
	} else {
		return false
	}
	if err != nil {
		return false
	}
	switch v := response.(type) {
	case *coltrace.ExportTraceServiceResponse:
		return v.GetPartialSuccess().GetRejectedSpans() == 0
	case *collogs.ExportLogsServiceResponse:
		return v.GetPartialSuccess().GetRejectedLogRecords() == 0
	case *colmetrics.ExportMetricsServiceResponse:
		return v.GetPartialSuccess().GetRejectedDataPoints() == 0
	}
	return false
}
func main() {
	listen := flag.String("listen", "127.0.0.1:6199", "private local interface")
	target := flag.String("target", "https://api.dagger.cloud", "original Cloud endpoint")
	spool := flag.String("spool", "", "private spool directory")
	paused := flag.Bool("paused", false, "start paused for replay validation")
	adminFile := flag.String("admin-file", "", "private administrative token file")
	flag.Parse()
	adminBytes, err := os.ReadFile(*adminFile)
	if err != nil || len(bytes.TrimSpace(adminBytes)) < 32 {
		panic("administrative token file required")
	}
	if *spool == "" {
		panic("spool required")
	}
	u, err := url.Parse(*target)
	if err != nil || u.Scheme != "https" || u.Host == "" || u.User != nil || u.RawQuery != "" || u.Fragment != "" {
		panic("HTTPS upstream base URL required")
	}
	client := &http.Client{Transport: &http.Transport{Proxy: http.ProxyFromEnvironment, ForceAttemptHTTP2: true, MaxIdleConns: 32, MaxIdleConnsPerHost: 16, IdleConnTimeout: 90 * time.Second}, CheckRedirect: func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse }}
	r, err := openRelay(*spool, u, client)
	if err != nil {
		panic(err)
	}
	defer r.close()
	r.admin = sha256.Sum256(bytes.TrimSpace(adminBytes))
	r.paused = *paused
	r.start(4)
	server := &http.Server{Addr: *listen, Handler: http.HandlerFunc(r.serve), ReadHeaderTimeout: 5 * time.Second}
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	go func() {
		<-ctx.Done()
		shutdown, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		server.Shutdown(shutdown)
	}()
	fmt.Println("relay ready; request payloads and headers are never logged")
	if err := server.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
		panic(err)
	}
}
