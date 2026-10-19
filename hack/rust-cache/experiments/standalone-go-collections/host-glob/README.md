# Standalone component comparison

`source.json` pins the upstream main and source branch. `summary.json`, `samples.json` and `steps.json` retain medians, all raw observations and exact commands. Build time and fixture setup are excluded.

The JSON overlays retain the original absolute paths. Adapt the checkout, module-cache and evidence prefixes to replay in a clean checkout of the pinned base. Both overlays use the same bench-N.go fixture files; only the candidate overlays the production-N.go files. The typed-method comparison instead overlays the one patched file of Dagger main's existing Dang dependency; its original module version remains pinned.

Build each binary using its recorded overlay and run it with the recorded -test arguments. Alternate A/B and B/A order four times. Component results do not establish a complete Go listing or cold-start gain. The actual source branch was separately checked with the package race detector.
