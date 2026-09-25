from pathlib import Path
import json
b=Path('/tmp/collections-perf/half-second')
s=Path('/home/dagger/dag/sdk/typescript/runtime/runtime_node.go').read_text()
old='''		WithEntrypoint([]string{
			"tsx", "--no-deprecation", "--tsconfig", n.cfg.tsConfigPath(), entrypointPath,
		})'''
new='''		WithEnvVariable("TSX_TSCONFIG_PATH", n.cfg.tsConfigPath()).
		WithMountedCache("/tmp/tsx-0", dag.CacheVolume("mod-tsx-transforms-"+n.cfg.runtimeVersion)).
		WithEntrypoint([]string{
			"node", "--import", "/usr/local/lib/node_modules/tsx/dist/loader.mjs", "--no-deprecation", entrypointPath,
		})'''
assert s.count(old)==2
s=s.replace(old,new)
(b/'runtime_node.go').write_text(s)
(b/'runtime-overlay.json').write_text(json.dumps({'Replace':{'/home/dagger/dag/sdk/typescript/runtime/runtime_node.go':str(b/'runtime_node.go')}}))
