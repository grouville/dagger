The two engines freeze the complete effective 6a82 diagnostic stack, including
its existing leaf fast path, combined Dang changes, static TypeScript prototype,
Address-default support, and previous discovery changes. The shared production
checkout and syntax-isolated dependency are not edited.

Both variants add only the same telemetry ForceFlush profiling boundaries. Their
sole behavior difference is the cloneSyntax implementation. Both compile with
one module replacement path and source revision 4f2ef6d700. The recipe copies
167 local dependency source and embedded files; all effective parent overlays
remain in force. The later CLI projection changes are restored/hidden in both
engine overlays so they do not alter the effective baseline. The CLI remains the
previously frozen d685 binary.

The preparation recorded two early source-guard failures before a recipe or
binary existed: the parent-to-current diff includes CLI/SDK source changes, and
sdk/go/artifacts.go did not exist at the parent revision. The final explicit
restore/delete overlays handle those facts. The partially copied input tree is
retained at ../engine-build-setup-partial-v1. No performance or behavior result
is associated with preparation failures.

Build output is not a performance measurement. The following whole-CLI trial
must validate ordinary warm listings, unique source edits, actual checks and
actual generation, with profiling separated from timing. Any microbenchmark
win remains a library result until the matched full-command comparison passes.
