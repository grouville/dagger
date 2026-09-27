# Source correction reviewed before tests

The new attachables package now declares the exact existing `dagger.io/engine.client` instrumentation constant. The old client constant remains unchanged, and the alias test checks equality. This resolves the missing-identifier blocker without changing trace/log scope or reintroducing the heavy client dependency.

The additional alias/constructor witness exercises assignments across both packages, provider method registration and returned concrete types. It lives in package `client`, so it is an exported-API alias compile witness, not an external-package test. The Unix socket test checks the actual filesystem socket provider, policy rejection and response bytes after input EOF, with deadlines and a joined owned accept goroutine. Existing lifetime tests retain real transport coverage.

No further source blocker was found. Compilation, normal/race execution and actual helper performance remain unperformed by this reviewer. The original report/input hashes remain intact as the pre-correction record; correction-hashes.json pins this later review.
