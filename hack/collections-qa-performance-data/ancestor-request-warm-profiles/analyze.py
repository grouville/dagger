"""Reduce separately collected fully primed profiles; no ordinary latency claim."""
from pathlib import Path
from collections import Counter
import json,hashlib
H=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def merge(xs):
 r=[]
 for a,b in sorted(xs):
  if r and a<=r[-1][1]:r[-1][1]=max(b,r[-1][1])
  else:r.append([a,b])
 return r
def union(xs):return sum(b-a for a,b in merge(xs))/1e6
def main():
 run=H/'results-v1';out=H/'results-v1-evidence';rows=json.loads((run/'results.json').read_text());rest=json.loads((run/'restoration.json').read_text())
 assert len(rows)==4 and all(r['correct']for r in rows) and all(rest[k]for k in ('fixtures_restored','engine_original_restored','engine_stopped'))
 assert not out.exists();out.mkdir()
 def write(n,v):(out/n).write_text(json.dumps(v,indent=2)+'\n')
 write('samples.json',rows);write('restoration.json',rest)
 profiles={}
 for i,row in enumerate(rows):
  if not row['profile']:continue
  d=run/f"{i:02d}-{row['block']}-{row['phase']}-{row['flow']}-{row['variant']}";path=d/'run.wcprof.private'
  with path.open()as f:header=json.loads(next(f));ops=[json.loads(l)for l in f if l.strip()]
  ops=[o for o in ops if o.get('e')=='op'];by_id={o['id']:o for o in ops};strings=header['strings'];origin=min(o['s']for o in ops)
  def name(o):return strings[o.get('c',0)]
  def span(o):return(o['s'],o['d'])
  def facts(oset):return {'count':len(oset),'inclusive_sum_ms':sum(o['d']-o['s']for o in oset)/1e6,'interval_union_ms':union([span(o)for o in oset]),'intervals':[{'start_ms':(o['s']-origin)/1e6,'duration_ms':(o['d']-o['s'])/1e6}for o in sorted(oset,key=lambda o:o['s'])]}
  parents=[o for o in ops if name(o)=='filesync.syncParentDirs'];hosts=[o for o in ops if o['k']=='call_exec'and name(o)=='Host.directory']
  queries=[o for o in ops if name(o)=='session.query'];per_host=[]
  for host in sorted(hosts,key=lambda o:o['s']):
   children=[]
   for parent in parents:
    cur=parent;seen=set()
    while cur and cur['id']not in seen:
     if cur['id']==host['id']:children.append(parent);break
     seen.add(cur['id']);cur=by_id.get(cur.get('p'))
   ints=[span(o)for o in children]
   per_host.append({'start_ms':(host['s']-origin)/1e6,'host_directory_ms':(host['d']-host['s'])/1e6,'parent_sync_count':len(children),'parent_sync_union_ms':union(ints),'remaining_host_interval_ms':(host['d']-host['s'])/1e6-union(ints),'pre_parent_ms':(min(o['s']for o in children)-host['s'])/1e6 if children else None,'post_parent_ms':(host['d']-max(o['d']for o in children))/1e6 if children else None})
  phase={}
  for label,kind,cl in [('workspace_artifacts','call_exec','Workspace.artifacts'),('collection_expansion','call_exec','Artifacts.__itemsJSON'),('git_advertisements','internal','git.publicAdvertisement'),('find_roots','call_exec','Workspace.findRoots'),('workspace_file','call_exec','Workspace.file'),('workspace_glob','call_exec','Workspace.glob'),('go_modules','call_exec','go:Go.modules')]:phase[label]=facts([o for o in ops if o['k']==kind and name(o)==cl])
  go_ops=[o for o in ops if o['k']=='call_exec' and name(o) in ('go:Go.modules','Go.modules')]
  workspace_reads=[]
  for o in ops:
   if o['k']!='call_exec' or name(o) not in ('Workspace.findRoots','Workspace.file'):continue
   cur=o;seen=set();go_ancestor=None;host_children=[]
   while cur and cur['id']not in seen:
    if cur in go_ops:go_ancestor=cur;break
    seen.add(cur['id']);cur=by_id.get(cur.get('p'))
   for h in hosts:
    cur=h;seen=set()
    while cur and cur['id']not in seen:
     if cur['id']==o['id']:host_children.append(h);break
     seen.add(cur['id']);cur=by_id.get(cur.get('p'))
   workspace_reads.append({'class':name(o),'start_ms':(o['s']-origin)/1e6,'duration_ms':(o['d']-o['s'])/1e6,'go_modules_parent_chain_proven':go_ancestor is not None,'temporally_enclosed_by_go_modules':any(g['s']<=o['s']and o['d']<=g['d']for g in go_ops),'host_directory_child_count':len(host_children),'host_directory_child_union_ms':union([span(h)for h in host_children])})
  profiles[row['variant']]={'profile_sha256':sha(path),'schema_version':header['schema_version'],'operation_count':len(ops),'operation_kinds':dict(Counter(o['k']for o in ops)),'dropped_events':header['dropped_events'],'open_operations':len(header.get('open_ops',[])),'instrumented_cli_seconds':row['seconds'],'operation_window_ms':(max(o['d']for o in ops)-origin)/1e6,'query_union_ms':union([span(o)for o in queries]),'parent_sync':facts(parents),'host_directory':facts(hosts),'parent_sync_hosts':per_host,'phases':phase,'workspace_read_details':workspace_reads,'go_module_operations':facts(go_ops),'subtree_measurement_limit':'There is no separate subtree marker in this build. Remaining Host.directory intervals include initial stat/path resolution, subtree sync, local mirror/filter/hash work; they are not pure subtree transfer duration. Nested/overlapping intervals must not be added to predict CLI savings.'}
  assert header['dropped_events']==0 and not header.get('open_ops') and parents
 write('profiles.json',profiles)

 details={}
 for i,row in enumerate(rows):
  if not row['profile']:continue
  path=run/f"{i:02d}-{row['block']}-{row['phase']}-{row['flow']}-{row['variant']}"/'run.wcprof.private'
  with path.open()as f:header=json.loads(next(f));allops=[json.loads(l)for l in f if l.strip()]
  ops=[o for o in allops if o.get('e')=='op'];strings=header['strings'];origin=min(o['s']for o in ops)
  name=lambda o:strings[o.get('c',0)]
  gos=[o for o in ops if o['k']=='call_exec'and name(o)in('go:Go.modules','Go.modules')]
  entries=[]
  for go in gos:
   nested=[o for o in ops if go['s']<=o['s']and o['d']<=go['d']]
   classes=[]
   for k,c in sorted({(o['k'],name(o))for o in nested}):
    matched=[o for o in nested if o['k']==k and name(o)==c]
    if k not in ('internal','call_exec'):continue
    classes.append({'kind':k,'class':c,'count':len(matched),'inclusive_sum_ms':sum(o['d']-o['s']for o in matched)/1e6,'union_ms':union([(o['s'],o['d'])for o in matched]),'maximum_ms':max(o['d']-o['s']for o in matched)/1e6})
   entries.append({'start_ms':(go['s']-origin)/1e6,'duration_ms':(go['d']-go['s'])/1e6,'relation':'Temporal enclosure, not proven cross-runtime parent ancestry. Inclusive classes overlap.','classes':sorted(classes,key=lambda c:-c['inclusive_sum_ms'])})
  details[row['variant']]=entries
 write('go-module-details.json',details)
 p=json.loads((run/'provenance.json').read_text());m=p['build_manifest']
 write('provenance.json',{'source_head':m['source_head'],'binary_sha256':{v:{k:m[v][k]['sha256']for k in('cli','engine')}for v in('baseline','candidate')},'driver_sha256':sha(run/'driver.py.txt'),'numeric_results_sha256':sha(run/'results.json'),'cache_boundary':p['cache_boundary'],'cloud_commands':0,'measured_implementation':'Frozen v1 Linux, not a separately measured v2 binary','profile_scope':'One ordinary full check-l primer immediately followed by its identical profile per variant. No restart or other commands between primer and profile. These are diagnostics, excluded from ordinary samples.'})
 lines=['Four local commands passed: one full check-list primer then one identical profiled check-list per variant. All four produced the exact14 rows. Original source/output/binary state was restored and the owned engine stopped. No Cloud calls.','','These profiles have a fully primed catalog boundary, unlike the earlier72-call profiles collected after restart plus only a selected-test warmup. They remain diagnostic observations; their profiled CLI times are excluded from ordinary performance medians.','','| Quantity | Baseline | Candidate |','| --- | ---: | ---: |']
 for title,fn in [('Profiled CLI ms',lambda p:p['instrumented_cli_seconds']*1000),('Query union ms',lambda p:p['query_union_ms']),('Parent-sync count',lambda p:p['parent_sync']['count']),('Parent-sync sum ms',lambda p:p['parent_sync']['inclusive_sum_ms']),('Parent-sync union ms',lambda p:p['parent_sync']['interval_union_ms']),('Host.directory union ms',lambda p:p['host_directory']['interval_union_ms']),('Workspace.artifacts ms',lambda p:p['phases']['workspace_artifacts']['inclusive_sum_ms']),('Expansion ms',lambda p:p['phases']['collection_expansion']['inclusive_sum_ms']),('Git advertisement union ms',lambda p:p['phases']['git_advertisements']['interval_union_ms']),('Go.modules ms',lambda p:p['go_module_operations']['inclusive_sum_ms']),('findRoots sum ms',lambda p:p['phases']['find_roots']['inclusive_sum_ms']),('Workspace.file sum ms',lambda p:p['phases']['workspace_file']['inclusive_sum_ms'])]:lines.append(f"| {title} | {fn(profiles['baseline']):.2f} | {fn(profiles['candidate']):.2f} |")
 lines+=['','Inclusive phases overlap; interval unions are not automatically critical-path savings. There is no dedicated subtree marker, so Host.directory remainder includes stat/path, subtree transfer and engine mirror/filter/hash work. go-module-details.json records temporal enclosure, not invented nested-runtime ancestry.','','The same profile marker exists in both engines. These frozen binaries measure v1 on Linux; the later v2 only adds Windows protocol-root acceptance and has separate test evidence. This host has roughly6000 entries in /tmp, increasing the opportunity from removing unrelated sibling enumeration. No service-up, cold-volume, Cloud or universal500ms claim follows.']
 (out/'report.md').write_text('\n'.join(lines)+'\n')
 for n in ('runtime.py','analyze.py'):(out/n).write_bytes((H/n).read_bytes())
 write('archive-allowlist.json',{'files':['samples.json','restoration.json','profiles.json','go-module-details.json','provenance.json','report.md','runtime.py','analyze.py'],'exclude':'Raw profiles, stdout/stderr, engine identifiers, credentials/config and source inputs.'})
 print(json.dumps({'evidence':str(out),'profiles':{v:{'parent_union_ms':p['parent_sync']['interval_union_ms'],'catalog_ms':p['phases']['workspace_artifacts']['inclusive_sum_ms'],'go_ms':p['go_module_operations']['inclusive_sum_ms']}for v,p in profiles.items()}}))
if __name__=='__main__':main()
