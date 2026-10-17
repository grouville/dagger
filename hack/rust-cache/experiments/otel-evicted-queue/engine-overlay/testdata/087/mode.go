package dang

import "sync/atomic"

// Diagnostic switch for a controlled comparison in the development engine.
var lazyTypeMapsDiagnostic atomic.Bool

func SetLazyTypeMapsDiagnostic(enabled bool) { lazyTypeMapsDiagnostic.Store(enabled) }
func LazyTypeMapsDiagnosticEnabled() bool    { return lazyTypeMapsDiagnostic.Load() }
