#!/usr/bin/env python3
from pathlib import Path
import hashlib,json,os,re,subprocess,time
ROOT=Path('/home/dagger/dag');P=Path(__file__).resolve().parent;B=P/'builds'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
r=json.loads((B/'build-recipe.json').read_text())
def guard():
 assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()==r['source_head']
 assert not subprocess.check_output(['git','status','--porcelain','--untracked-files=all'],cwd=ROOT,text=True).strip(),'source tree changed after clean recipe freeze'
 for name,digest in r['inputs'].items():assert sha(Path(name))==digest,name
 assert sha(Path(r['cli']['path']))==r['cli']['sha256']
guard();env=os.environ.copy();env.update(r['environment']);records={}
assert not (B/'runtime-builds.json').exists()
for variant,cmd in r['commands'].items():
 guard();assert not Path(cmd[cmd.index('-o')+1]).exists()
 started=time.monotonic()
 with(B/('build-'+variant+'.log')).open('w')as log:p=subprocess.run(cmd,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=600)
 assert p.returncode==0,variant
 binary=Path(cmd[cmd.index('-o')+1]);info=subprocess.check_output([r['toolchain'],'version','-m',str(binary)],cwd=ROOT,env=env,text=True)
 (B/(variant+'-build-info.txt')).write_text(info)
 revision=re.search(r'vcs.revision=(\S+)',info);modified=re.search(r'vcs.modified=(\S+)',info)
 assert revision and revision.group(1)==r['source_head'] and modified and modified.group(1)=='false'
 records[variant]={'path':str(binary),'sha256':sha(binary),'seconds':time.monotonic()-started,'vcs_revision':revision.group(1),'vcs_modified':False,'build_info_sha256':sha(B/(variant+'-build-info.txt'))}
 (B/'build-progress.json').write_text(json.dumps(records,indent=2)+'\n')
guard()
v={'recipe_path':str(B/'build-recipe.json'),'recipe_sha256':sha(B/'build-recipe.json'),'source_head':r['source_head'],'expected_core_version':r['expected_core_version'],'variants':records,'cli':r['cli'],'image':r['common_image'],'common_sdk_inputs':r['common_sdk_inputs'],'common_go_module':r['common_go_module'],'scope':r['source_scope']}
(B/'runtime-builds.json').write_text(json.dumps(v,indent=2)+'\n')
print(json.dumps(v,indent=2))
