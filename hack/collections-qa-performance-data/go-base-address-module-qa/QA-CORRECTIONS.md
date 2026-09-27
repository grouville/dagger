# Corrections to the private GoDev QA

The initial setup asserted a BusyBox tag appeared once in the full upstream QA source, but it also occurs in another existing fixture. Pinning is now scoped to addressBase. No engine call happened in that setup attempt.

The first actual check exposed two newly authored bare rescue catches rejected by Dang inference. Both now use `err: Error =>`, as existing GoDev tests do. Parsing alone had not detected this semantic error.

The second check passed inference and discovered modules/tests with an always-failing Address producer, then failed `tool.base == null`. This expression does not inspect the server's nullable field: GraphQLFunction.Call returns a lazy GraphQLValue for non-scalar output, and equality checks proxy/null identity without querying. The effective Dang eval.go and ast.go preserve this distinction. The new QA removes only that invalid assertion; successful discovery and eventual exact producer-error propagation still prove the intended behavior. The version/null assertion is scalar and does execute its query.

Candidate go.dang and engine binary never changed. The third planned suite retains all constructor-policy, discovery, execution, service, test and generation checks; it is not yet run. No broader optional-value semantics change or additional cache behavior is introduced.
