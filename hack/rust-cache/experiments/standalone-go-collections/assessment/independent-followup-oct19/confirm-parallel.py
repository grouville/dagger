from pathlib import Path
import json,statistics,subprocess,time
from benchmark_helpers import run,engine_info
out=Path('/tmp/go-collection-upstream-review-oct19')
engine=engine_info('dagger-collection-standalone-main-oct19','tcp://127.0.0.1:16310','http://127.0.0.1:16130')
rows=[]
for count,pairs in [(1,4),(16,4)]:
 arms={}
 for arm,module in [('before',Path('/tmp/go-collection-clean-go-main')),('candidate',out/'go-parallel-discovery')]:
  root=out/f'parallel-fixed-config-{count}'/arm;root.mkdir(parents=True)
  subprocess.run(['git','init','--quiet',str(root)],check=True)
  (root/'go.mod').write_text('module example.com/collectionfixture\n\ngo 1.26.6\n')
  (root/'dagger.toml').write_text('[modules.go]\nsource = "'+str(module)+'"\n[modules.go.settings]\nversion = "1.26.6"\ngoflags = "-p=8"\ntest = ["**"]\n')
  for i in range(count):
   p=root/f'mod_{i:03d}';p.mkdir();(p/'go.mod').write_text(f'module example.com/mod{i}\n\ngo 1.26.6\n');(p/'value.go').write_text('package fixture\nfunc Value() int { return 42 }\n');(p/'value_test.go').write_text('package fixture\nimport "testing"\nfunc TestValue(t *testing.T) { if Value()!=42 {t.Fatal("value")} }\n')
  source=root/'mod_000/value.go';test=root/'mod_000/value_test.go'
  arms[arm]=dict(root=root,source=source,test=test,s=source.read_bytes(),t=test.read_bytes())
 try:
  for pair in range(-2,pairs):
   previous=None
   for arm in (['before','candidate'] if pair%2==0 else ['candidate','before']):
    f=arms[arm];tag=f'{count}-{pair}'
    f['source'].write_bytes(f['s']+f'\n// Source edit {tag}\n'.encode());f['test'].write_bytes(f['t']+f'\n// Test edit {tag}\n'.encode()+(b'\nfunc TestAddedReview(t *testing.T) {}\n' if pair==-2 else b''))
    label=f'parallel-fixed-{count}-{pair}-{arm}';print(json.dumps(dict(event='listing-start',label=label)),flush=True)
    metrics,text,log=run(label,f['root'],['check','--module','go','--check','test','--list','--all'],engine)
    lines=[l for l in text.splitlines() if l.startswith('go ')];names=[tuple(l.split()[1:3]) for l in lines];wanted=sorted([(f'mod_{i:03d}','TestValue') for i in range(count)]+([('mod_000','TestAddedReview')] if pair==-2 else []))
    row=dict(modules=count,pair=pair,arm=arm,warmup=pair<0,rows=len(lines),correct_names=names==wanted,matching_rows=previous is None or previous==lines,fixed_configuration=True,fresh_cli=True,source_edit=True,test_edit=True,telemetry=True,profiling=False,log=log,**metrics);rows.append(row);(out/'parallel-fixed-samples.json').write_text(json.dumps(rows,indent=2)+'\n');print(json.dumps(row),flush=True)
    assert row['cleanup_successful'] and row['correct_names'] and row['matching_rows'],row
    previous=lines
 finally:
  for f in arms.values():f['source'].write_bytes(f['s']);f['test'].write_bytes(f['t'])
summary=[]
for count in [1,16]:
 r=[x for x in rows if x['modules']==count and not x['warmup']];b=sorted([x for x in r if x['arm']=='before'],key=lambda x:x['pair']);c=sorted([x for x in r if x['arm']=='candidate'],key=lambda x:x['pair'])
 item=dict(modules=count,pairs=len(b),faster_pairs=sum(y['seconds']<x['seconds'] for x,y in zip(b,c)))
 for key in ['seconds','engine_cpu','allocated_bytes','allocations','peak_memory_current']:item['before_'+key]=statistics.median(x[key] for x in b);item['candidate_'+key]=statistics.median(x[key] for x in c)
 summary.append(item)
(out/'parallel-fixed-summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(dict(event='complete',summary=summary)),flush=True)
