package server

import "context"

// Diagnostic only; do not change GC policy or delete cache entries.
func (srv *Server) MeasureCacheUsageDiagnostic(ctx context.Context, enabled bool) (map[string]any, error) {
	srv.gcmu.Lock()
	defer srv.gcmu.Unlock()
	return srv.engineCache.MeasureUsageDiagnostic(ctx, enabled)
}
