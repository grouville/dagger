from pathlib import Path
import hashlib,json,subprocess,time
root=Path(__file__).parent
work=Path('/tmp/dagger-cache-usage-provider-rows')
go='/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go'
rows=[]
for arm in ['before','after']:
 command=[go,'test','-p','2','-buildvcs=false','-c','-o',str(root/(arm+'.test'))]
 if arm=='before':command+=['-overlay',str(root/'before-overlay.json')]
 command+=['./dagql']
 start=time.monotonic()
 with (root/(arm+'-build.log')).open('w') as out:r=subprocess.run(command,cwd=work,stdout=out,stderr=subprocess.STDOUT)
 row=dict(arm=arm,command=command,exit_code=r.returncode,seconds=time.monotonic()-start)
 if r.returncode==0:row['sha256']=hashlib.sha256((root/(arm+'.test')).read_bytes()).hexdigest()
 rows.append(row);(root/'bench-builds.json').write_text(json.dumps(rows,indent=2)+'\n')
 print(arm,r.returncode,flush=True)
 assert r.returncode==0,arm
