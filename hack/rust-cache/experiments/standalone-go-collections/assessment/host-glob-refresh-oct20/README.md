# Host-glob CLI: interrupted older-baseline attempt

The published host-glob patch f5fe8d7e9454cc7e360b7ed03a68f6323095d3bf was independently applied to Dagger main ce6dc9f9403b52067f5831149eab4871f857185d. Matching/cancellation race checks pass on main and the patch, and a matching CLI was built. The actual full listing used the unchanged ce6 engine, Go module334136faaa1cd36ac26dfdc648eda907ce99c063 and the same real Dagger source as the prior attempt.

The CLI remained live with zero output rows after 441.19 seconds. It was intentionally interrupted after discovering newer upstream Go and Dagger commits, so that investigation could move to the refreshed baseline. The driver restored all edited source. The interruption record identifies the verified process group and reason. This is not a timeout at that duration, a successful completed listing or a speedup measurement. Partial CPU/allocation counters do not establish total-work savings or regressions.

All engines and volumes remain retained. The refreshed independent Go sorting study is in the sibling go-ordered-paths-oct20 archive; its file-discovery numbers must not be attributed to this host-glob CLI attempt.
