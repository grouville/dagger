The 240-file engine evidence bundle is a reproducibility snapshot, not a
240-file proposed upstream change.

The new behavioral change is only `cloneSyntax` in `pkg/dang/parse_cache.go`,
with focused ownership/error/budget tests. It applies to the retained
experimental syntax-cache implementation; it is not an assertion that ordinary
Dang v2.1.4 already includes this cache. The prior scalar/nil fast path is in
both measured engine variants and is excluded from the new improvement claim.

The frozen 180-file local dependency and the inherited engine overlays record
the effective prior stack. They are unchanged context, not newly authored
optimizations. Both variants also have identical fixed-label telemetry-flush
profiling markers, supplied solely to explain barrier work in separate
profiling calls. Neither includes the proposed narrower flush behavior.

The build-only module replacement path and source overlays isolate inputs and
preserve the actual baseline. They are not a proposed module/engine API or a
new production caching mechanism. Normal CLI timing and correctness are the
next adoption gate; the completed library microbenchmarks do not prove a
whole-command gain.
