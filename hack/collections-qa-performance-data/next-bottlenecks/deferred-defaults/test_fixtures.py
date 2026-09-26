"""Run only when granted the engine slot. Original SDKs, normal CLI, no static guard resealing."""
import argparse,json,os,subprocess,time
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--cli',required=True);p.add_argument('--sdk',choices=['go','typescript','dang'],required=True);p.add_argument('--output',required=True);a=p.parse_args()
root=Path('/tmp/collections-perf/deferred-defaults/fixtures')/a.sdk
output=Path(a.output);output.mkdir(parents=True,exist_ok=True);rows=[]
if not (root/'.git').exists():subprocess.run(['git','init','-q',str(root)],check=True)
def run(label,args,want=None,error=None):
 start=time.perf_counter();r=subprocess.run([a.cli,*args],cwd=root,env=os.environ,capture_output=True,text=True);elapsed=time.perf_counter()-start
 (output/(label+'.stdout')).write_text(r.stdout);(output/(label+'.stderr')).write_text(r.stderr)
 row={'label':label,'args':args,'seconds':elapsed,'exit':r.returncode};rows.append(row);(output/'samples.json').write_text(json.dumps(rows,indent=2)+'\n')
 if error:assert r.returncode and error in r.stdout+r.stderr,(row,r.stderr)
 else:
  assert r.returncode==0,(row,r.stderr)
  if want is not None:assert r.stdout.strip()==want.strip(),(row,r.stdout)
 return r.stdout
original=(root/'dagger.toml').read_text()
try:
 # Force constructor execution in the consumer while leaving its base unused.
 (root/'dagger.toml').write_text(original.replace('constructor-fail = false','constructor-fail = true'))
 run('unused-constructor-fails',['api','call','unused'],'unused')
 listing=run('expanded-list-constructor-fails',['check','-l','--all']);assert 'items/verify' in listing
 run('used-constructor-fails',['api','call','used'],error='constructor sentinel')
 (root/'dagger.toml').write_text(original);(root/'body.txt').write_text('fail')
 run('unused-body-fails',['api','call','unused'],'unused')
 run('used-body-fails',['api','call','used'],error='body sentinel')
 (root/'body.txt').write_text('ok')
 for value in ['one','two','one']:
  (root/'payload/value.txt').write_text(value+'\n')
  run('used-'+value+'-'+str(len(rows)),['api','call','used'],value+'\n'+value)
  run('returned-'+value+'-'+str(len(rows)),['api','call','returned','file','--path','/value.txt','contents'],value)
 run('check-execution',['check','--all'])
 for address,sentinel in [('dag://producer/missing','no artifact matches'),('dag://producer/wrong','not a Container')]:
  (root/'dagger.toml').write_text(original.replace('dag://producer/base',address))
  run('invalid-'+address.rsplit('/',1)[-1],['api','call','unused'],error=sentinel)
finally:
 (root/'dagger.toml').write_text(original);(root/'constructor.txt').write_text('ok');(root/'body.txt').write_text('ok');(root/'payload/value.txt').write_text('one\n')
print(json.dumps(rows,indent=2))
