# fix: search explicit paths created by workspace overlays

`Workspace.search(paths: ["/created.txt"])` fails when `created.txt` was added with `withNewFile` in a host-backed workspace. The search sends that path to the host's ripgrep before merging overlay results. Ripgrep fails because the file exists only in the engine. The same problem affects a new parent directory and a list mixing host and overlay files.

Keep overlay-owned paths out of the host search and merge overlay results even when every requested path comes from the overlay. For a parent shared by the host and overlay, check the base source before deciding whether to search it. Unrelated missing paths still report the original error.

The regression reproduces all three failures through the real CLI and API on current main. With the fix, all four integration cases pass, including the missing-path check. The focused source-path and merge tests pass under the race detector. The Go module's collection and retained-package checks also pass, covering overlays, Unicode, stable ordering and selected execution. All six retained Rust histories reuse every compilation action across the engine replacement.

This fixes correctness and enables a separate discovery experiment. A listing-speed improvement from this engine fix is unmeasured. It adds no shared state or locks; the additional existence check runs only for ancestors of overlay edits or mounts.

[Source on the fork](https://github.com/grouville/dagger/tree/fix/workspace-search-host-overlays), commit `744ec940`. Based directly on main `ff0b029a4d`. No PR is open.
