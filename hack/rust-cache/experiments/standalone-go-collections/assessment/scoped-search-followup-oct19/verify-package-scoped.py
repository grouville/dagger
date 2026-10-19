from pathlib import Path
import hashlib,json,statistics,subprocess,time
from benchmark_helpers import run,engine_info
out=Path('/tmp/go-collection-upstream-review-oct19')
checks=json.loads((out/'scoped-package-checks.json').read_text())
assert checks[-1]['label']=='scoped-collection-execution' and checks[-1]['exit_code']==0
engine=engine_info('dagger-collection-standalone-main-oct19','tcp://127.0.0.1:16310','http://127.0.0.1:16130')
main=Path('/tmp/go-collection-clean-go-main');candidate=out/'go-package-workspace'
rows=[]
def fixture(phase,packages,files,arm,module):
 root=out/f'{phase}-{packages}-packages-{files}-files'/arm;root.mkdir(parents=True,exist_ok=True)
 subprocess.run(['git','init','--quiet',str(root)],check=True)
 (root/'go.mod').write_text('module example.com/packagefixture\n\ngo 1.26.6\n')
 config='[modules.go]\nsource = "'+str(module)+'"\n[modules.go.settings]\nversion = "1.26.6"\ngoflags = "-p=8"\ntest = ["**"]\n'
 (root/'dagger.toml').write_text(config)
 expected=[]
 for n in range(packages):
  package=root/f'pkg_{n:03d}';package.mkdir()
  (package/'value.go').write_text('package fixture\n\nfunc Value() int { return 42 }\n')
  for f in range(files):
   source='package fixture\n\nimport "testing"\n'
   for t in range(8):
    name=f'TestCase{f*8+t:03d}';source+=f'\nfunc {name}(t *testing.T) {{ if Value()!=42 {{ t.Fatal("wrong value") }} }}\n';expected.append((f'pkg_{n:03d}',name))
   (package/f'value_{f:03d}_test.go').write_text(source)
 source=root/'pkg_000/value.go';test=root/'pkg_000/value_000_test.go'
 return dict(root=root,source=source,test=test,source_bytes=source.read_bytes(),test_bytes=test.read_bytes(),expected=expected,config=config)
# A/A compares equal source trees on main. A/B changes only the Go module code.
for phase,packages,files,pairs in [('scoped-aa-control',16,1,2),('scoped-package',1,1,4),('scoped-package',1,16,4),('scoped-package',16,1,4)]:
 arms={arm:fixture(phase,packages,files,arm,main if arm=='before' or phase=='scoped-aa-control' else candidate) for arm in ['before','candidate']}
 try:
  for pair in range(-2,pairs):
   previous=None
   for arm in (['before','candidate'] if pair%2==0 else ['candidate','before']):
    f=arms[arm]
    assert (f['root']/'dagger.toml').read_text()==f['config'],'Configuration changed during the comparison.'
    # Both arms see the same source bytes in each pair; their Git roots and configs stay fixed.
    tag=f'{phase}-{packages}-{files}-{pair}'
    edited_test = f['test_bytes']
    if pair >= 0:
     assert edited_test.count(b'func TestCase000(')==1
     edited_test=edited_test.replace(b'func TestCase000(', f'func TestCase000Edit{pair}('.encode(), 1)
    f['source'].write_bytes(f['source_bytes']+f'\n// Scoped search source edit {tag}\n'.encode())
    f['test'].write_bytes(edited_test+f'\n// Scoped search test edit {tag}\n'.encode()+(b'\nfunc TestAddedReview(t *testing.T) {}\n' if pair==-2 else b''))
    label=f'{phase}-{packages}-{files}-{pair}-{arm}';print(json.dumps(dict(event='listing-start',label=label)),flush=True)
    lock=f['root']/'dagger.lock';before_lock=hashlib.sha256(lock.read_bytes()).hexdigest() if lock.exists() else None
    metrics,text,log=run(label,f['root'],['check','--module','go','--check','test','--list','--all'],engine)
    lines=[line for line in text.splitlines() if line.startswith('go ')];names=[tuple(line.split()[1:3]) for line in lines];wanted=sorted([(pkg, f'TestCase000Edit{pair}' if pair>=0 and pkg=='pkg_000' and name=='TestCase000' else name) for pkg,name in f['expected']]+([('pkg_000','TestAddedReview')] if pair==-2 else []))
    row=dict(phase=phase,packages=packages,test_files_per_package=files,tests_per_file=8,pair=pair,arm=arm,warmup=pair<0,rows=len(lines),correct_names=names==wanted,matching_rows=previous is None or previous==lines,log=log,telemetry=True,profiling=False,fresh_cli=True,source_edit=True,test_edit=True,test_name_edit=pair>=0,fixed_configuration=True,lock_before_sha256=before_lock,lock_after_sha256=hashlib.sha256(lock.read_bytes()).hexdigest() if lock.exists() else None,**metrics)
    rows.append(row);(out/'package-scoped-samples.json').write_text(json.dumps(rows,indent=2)+'\n');print(json.dumps(row),flush=True)
    assert row['cleanup_successful'] and row['correct_names'] and row['matching_rows'],row
    previous=lines
 finally:
  for f in arms.values():f['source'].write_bytes(f['source_bytes']);f['test'].write_bytes(f['test_bytes'])
 summary=[]
 for key in sorted({(r['phase'],r['packages'],r['test_files_per_package']) for r in rows}):
  rs=[r for r in rows if (r['phase'],r['packages'],r['test_files_per_package'])==key and not r['warmup']]
  b=sorted([r for r in rs if r['arm']=='before'],key=lambda r:r['pair']);c=sorted([r for r in rs if r['arm']=='candidate'],key=lambda r:r['pair'])
  item=dict(phase=key[0],packages=key[1],test_files_per_package=key[2],rows=key[1]*key[2]*8,pairs=len(b),faster_pairs=sum(y['seconds']<x['seconds'] for x,y in zip(b,c)),median_paired_saving=statistics.median(x['seconds']-y['seconds'] for x,y in zip(b,c)))
  for metric in ['seconds','engine_cpu','allocated_bytes','allocations','peak_memory_current']:
   item['before_'+metric]=statistics.median(r[metric] for r in b);item['candidate_'+metric]=statistics.median(r[metric] for r in c)
  summary.append(item)
 (out/'package-scoped-summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(dict(event='case-complete',summary=summary[-1])),flush=True)
(out/'package-scoped-complete.json').write_text(json.dumps(dict(complete=True,commands=len(rows)),indent=2)+'\n')
