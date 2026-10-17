from pathlib import Path
import hashlib,json,subprocess,time
root=Path(__file__).parent
go='/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go'
before='/tmp/rust-cache-sipsma-review/dang-module-blueprint-content-key';after='/tmp/dang-direct-builtin-receivers'
jobs=[('baseline-guards',before,[go,'test','-p','2','-race','-overlay',str(root/'baseline-tests-overlay.json'),'-count=1','-run','TestBuiltinReceiver','./pkg/dang'])]
for arm,cwd in [('before',before),('after',after)]:
 command=[go,'test','-p','2','-c','-o',str(root/(arm+'.test'))]
 if arm=='before':command+=['-overlay',str(root/'baseline-tests-overlay.json')]
 jobs.append((arm+'-build',cwd,[*command,'./pkg/dang']))
rows=[]
for label,cwd,command in jobs:
 started=time.monotonic()
 with (root/(label+'.log')).open('w') as out:r=subprocess.run(command,cwd=cwd,stdout=out,stderr=subprocess.STDOUT)
 row=dict(label=label,cwd=cwd,command=command,exit_code=r.returncode,seconds=time.monotonic()-started)
 rows.append(row);(root/'component-builds.json').write_text(json.dumps(rows,indent=2)+'\n');print(label,r.returncode,flush=True);assert r.returncode==0,label
(root/'component-binaries.json').write_text(json.dumps({arm:dict(sha256=hashlib.sha256((root/(arm+'.test')).read_bytes()).hexdigest(),bytes=(root/(arm+'.test')).stat().st_size) for arm in ['before','after']},indent=2)+'\n')
