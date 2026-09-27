import difflib, hashlib, json, pathlib, subprocess
repo=pathlib.Path('/home/dagger/dag'); out=pathlib.Path('/tmp/collections-perf/ancestor-request-v1')
changed={}
def change(rel, transform):
    old=(repo/rel).read_text();new=transform(old)
    if old==new: raise RuntimeError('unchanged '+rel)
    dst=out/(rel.replace('/','-'))
    dst.write_text(new);changed[rel]={'original':old,'source':str(dst)}
def replace_once(s,a,b):
    if s.count(a)!=1:raise RuntimeError(f'anchor count {s.count(a)}: {a[:100]}')
    return s.replace(a,b,1)
change('engine/opts.go',lambda s:replace_once(s,'type LocalImportOpts struct {\n','type LocalImportOpts struct {\n\t// ParentDirsOnly requests literal ancestor directory metadata, without\n\t// enumerating siblings. Include/exclude patterns remain for older clients.\n\tParentDirsOnly bool `json:"parent_dirs_only,omitempty"`\n'))
change('engine/filesync/remotefs.go',lambda s:replace_once(replace_once(s,'\tuseGitIgnore bool\n','\tuseGitIgnore bool\n\tparentDirsOnly bool\n'),'\t\tPath:            fs.clientPath,\n','\t\tPath:            fs.clientPath,\n\t\tParentDirsOnly:  fs.parentDirsOnly,\n'))
change('engine/filesync/filesyncer.go',lambda s:replace_once(s,'\tremote := newRemoteFS(callerConn, root, includes, excludes, nil, false)\n','\tremote := newRemoteFS(callerConn, root, includes, excludes, nil, false)\n\t// Keep the existing filter request intact for clients that do not yet\n\t// recognize the metadata-only operation. Root or non-literal patterns\n\t// retain the general traversal on every client.\n\tremote.parentDirsOnly = engine.IsLiteralParentDirectoryTarget(include)\n'))
change('engine/client/filesync.go',lambda s:replace_once(s,'\tswitch {\n\tcase opts.GetAbsPathOnly:', '''\tif opts.ParentDirsOnly {
\t\tif err := opts.ValidateParentDirectoryMetadataRequest(); err != nil {
\t\t\treturn status.Errorf(codes.InvalidArgument, "invalid parent-directory request: %v", err)
\t\t}
\t\t// The wire operation is rooted at the client's filesystem or volume
\t\t// root, as syncParentDirs has always been. Never reinterpret arbitrary
\t\t// include/exclude requests as permission to walk another source root.
\t\tif !filepath.IsAbs(absPath) || filepath.Clean(absPath) != filepath.VolumeName(absPath)+string(filepath.Separator) {
\t\t\treturn status.Error(codes.InvalidArgument, "parent-directory request must use a filesystem root")
\t\t}
\t\tchain, err := fsutil.NewParentMetadataFS(absPath, filepath.FromSlash(opts.IncludePatterns[0]))
\t\tif err != nil {
\t\t\treturn fmt.Errorf("prepare parent-directory metadata: %w", err)
\t\t}
\t\tfiltered, err := fsutil.NewFilterFS(chain, &fsutil.FilterOpt{
\t\t\tIncludePatterns: opts.IncludePatterns,
\t\t\tExcludePatterns: opts.ExcludePatterns,
\t\t\tMap: func(_ string, st *fstypes.Stat) fsutil.MapResult {
\t\t\t\tnormalizeLocalImportStat(st)
\t\t\t\treturn fsutil.MapResultKeep
\t\t\t},
\t\t})
\t\tif err != nil {
\t\t\treturn fmt.Errorf("filter parent-directory metadata: %w", err)
\t\t}
\t\treturn fsutil.Send(stream.Context(), stream, filtered, nil)
\t}

\tswitch {
\tcase opts.GetAbsPathOnly:'''))
(out/'source-snapshot.json').write_text(json.dumps({'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip(),'inputs':{k:{'original_sha256':hashlib.sha256(v['original'].encode()).hexdigest(),'source':v['source'],'sha256':hashlib.sha256(pathlib.Path(v['source']).read_bytes()).hexdigest()} for k,v in changed.items()},'scope':'isolated source-only explicit parent metadata request; no tests/build/runtime'},indent=2)+'\n')
(out/'source-map.json').write_text(json.dumps({str(repo/k):v['source'] for k,v in changed.items()},indent=2)+'\n')
