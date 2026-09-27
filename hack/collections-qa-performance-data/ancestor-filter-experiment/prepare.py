from pathlib import Path
import hashlib,json,subprocess,difflib
repo=Path('/home/dagger/dag'); out=Path(__file__).parent
base=repo/'internal/fsutil/filter.go'; original=base.read_text()
needle='\treturn &filterFS{\n\t\tfs:                 fs,'
assert original.count(needle)==1
replacement='''\t// A literal path with all of its children excluded needs only its parent
	// chain. Keep the ordinary filter around it for matching, mapping, and
	// delayed parent emission; only the host traversal changes.
	if host, ok := fs.(*fs); ok {
		if target, ok := parentChainTarget(opt); ok {
			fs = &parentChainFS{fs: host, target: target}
		}
	}

	return &filterFS{
		fs:                 fs,'''
# Parameter fs shadows concrete fs type; use a helper which does the type assertion.
replacement='''\tfs = parentChainFilterFS(fs, opt)

	return &filterFS{
		fs:                 fs,'''
new=original.replace(needle,replacement)
(out/'filter.go').write_text(new)
paths={'internal/fsutil/filter.go':out/'filter.go','internal/fsutil/parent_chain.go':out/'parent_chain.go','internal/fsutil/parent_chain_linux.go':out/'parent_chain_linux.go','internal/fsutil/parent_chain_other.go':out/'parent_chain_other.go','internal/fsutil/parent_chain_test.go':out/'parent_chain_test.go'}
(out/'overlay.json').write_text(json.dumps({'Replace':{str(repo/p):str(q) for p,q in paths.items()}},indent=2)+'\n')
(out/'source-overlay.json').write_text(json.dumps({'Replace':{str(repo/p):str(q) for p,q in paths.items() if not p.endswith('_test.go')}},indent=2)+'\n')
(out/'manifest.json').write_text(json.dumps({'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip(),'base_filter_sha256':hashlib.sha256(base.read_bytes()).hexdigest(),'scope':'source-only, no shared source modifications'},indent=2)+'\n')
(out/'filter.patch').write_text(''.join(difflib.unified_diff(original.splitlines(True),new.splitlines(True),fromfile='a/internal/fsutil/filter.go',tofile='b/internal/fsutil/filter.go')))
