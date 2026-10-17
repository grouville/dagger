package dang

import "sync/atomic"

// Diagnostic switch for a controlled comparison in the development engine.
var callbackCallerReuseDiagnostic atomic.Bool

func SetCallbackCallerReuseDiagnostic(enabled bool) { callbackCallerReuseDiagnostic.Store(enabled) }
func CallbackCallerReuseDiagnosticEnabled() bool    { return callbackCallerReuseDiagnostic.Load() }
