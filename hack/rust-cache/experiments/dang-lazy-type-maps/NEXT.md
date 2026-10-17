# Next profile-driven experiments

The lazy-map full-command comparison is running; do not overlap heavy tests or change its engine modes while it runs.

## Native builtin method dispatch

`BoundBuiltinMethod.Call` (pkg/dang/eval.go) allocates a new Type, Object, two runtime maps and a self cell on every native String/List/Map method call. The generated method wrapper in `addBuiltinFunctions` uses that scope only to read its receiver (`scope.Self()`), then invokes `BuiltinDef.Impl`. Consider passing the receiver directly for these generated wrappers, with the existing path preserved for custom BuiltinFunction callbacks. Audit external CallFn mutation and keep defaults, block contexts, captured closures, exceptions and concurrent calls equivalent. Use allocation-profile call edges before prioritizing it. No patch has been implemented yet.

## Module string sorting

Three helpers in go.dang and gomod/main.dang implement insertion sorting with reduce and list concatenation. Even sorted inputs repeatedly copy a growing accumulator. Existing Dang v2.1.4 has no native List sort. A native primitive sort or keyed sort could address the algorithm for all modules, but is a language API addition and must be measured separately from the lazy-map fix.

Do not simply remove sorting: filepath.WalkDir sorts entries within each directory, but does not globally byte-sort file paths. A directory `a` with `a/b.go` can precede the sibling `a.go`, although Go byte order requires `a.go` before `a/b.go` (`.` < `/`). Workspace overlay/mount merge paths do sort globally. All source kinds and Unicode ordering must remain equivalent.
