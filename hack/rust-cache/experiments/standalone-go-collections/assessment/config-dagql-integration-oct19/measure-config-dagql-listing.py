from pathlib import Path
import json,statistics,subprocess,time
from config_dagql_benchmark_helpers import engine_info,run
out=Path('/tmp/go-collection-upstream-review-oct19')
root=out/'config-dagql-listing-fixture'
root.mkdir()
subprocess.run(['git','init','--quiet',str(root)],check=True)
(root/'dagger.toml').write_text('[modules.go]\nsource = "/tmp/go-collection-clean-go-main"\n[modules.go.settings]\nversion = "1.26.6"\ngoflags = "-p=8"\ntest = ["**"]\n')
(root/'go.mod').write_text('module example.com/configcache\n\ngo 1.26.6\n')
for i in range(16):
 package=root/f'pkg_{i:03d}'
 package.mkdir()
 (package/'value.go').write_text('package fixture\nfunc Value() int { return 42 }\n')
 (package/'value_test.go').write_text('package fixture\nimport "testing"\nfunc TestValue(t *testing.T) { if Value()!=42 {t.Fatal("value")} }\n')
engines={arm:engine_info(info['name'],info['runner'],info['debug']) for arm,info in json.loads((out/'config-dagql-engines.json').read_text()).items()}
source=root/'pkg_000/value.go';test=root/'pkg_000/value_test.go'
original_source,original_test=source.read_bytes(),test.read_bytes()
records=[]
try:
 for pair in range(-2,4):
  for arm in (['main','candidate'] if pair%2==0 else ['candidate','main']):
   name='TestEdited'+str(time.time_ns())
   comment=f'\n// Source edit {pair} {arm}\n'.encode()
   source.write_bytes(original_source+comment)
   assert original_test.count(b'func TestValue(')==1
   test.write_bytes(original_test.replace(b'func TestValue(',('func '+name+'(').encode(),1)+comment)
   label=f'config-dagql-listing-{pair}-{arm}'
   print(json.dumps(dict(event='start',label=label)),flush=True)
   metrics,text,log=run(label,root,['check','--module','go','--check','test','--list','--all'],engines[arm])
   rows=[line.split()[1:3] for line in text.splitlines() if line.split() and line.split()[0]=='go']
   expected=[[f'pkg_{i:03d}',name if i==0 else 'TestValue'] for i in range(16)]
   record=dict(pair=pair,arm=arm,warmup=pair<0,correct_names=rows==expected,rows=len(rows),unique_test_name=name,telemetry=True,fresh_cli=True,source_edit=True,test_edit=True,log=log,**metrics)
   records.append(record)
   (out/'config-dagql-listing-samples.json').write_text(json.dumps(records,indent=2)+'\n')
   print(json.dumps(record),flush=True)
   assert record['correct_names'] and record['cleanup_successful'],record
finally:
 source.write_bytes(original_source);test.write_bytes(original_test)
main=[r for r in records if r['arm']=='main' and not r['warmup']]
candidate=[r for r in records if r['arm']=='candidate' and not r['warmup']]
summary=dict(pairs=len(main),faster_pairs=sum(a['seconds']<b['seconds'] for a,b in zip(candidate,main)))
for arm,rows in [('main',main),('candidate',candidate)]:
 summary[arm]={key:statistics.median(r[key] for r in rows) for key in ['seconds','engine_cpu','allocated_bytes','allocations','peak_memory_current']}
(out/'config-dagql-listing-summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary),flush=True)
