from pathlib import Path
import json,subprocess,hashlib
D=Path(__file__).resolve().parent;B=D/'builds';R=Path('/home/dagger/dag');m=json.loads((B/'manifest.json').read_text());r=json.loads((B/'recipe.json').read_text())
assert hashlib.sha256(Path(m['engine']['path']).read_bytes()).hexdigest()==m['engine']['sha256']
info=subprocess.check_output([r['build_command'][0],'version','-m',m['engine']['path']],text=True)
settings={}
for line in info.splitlines():
 parts=line.strip().split('\t')
 if len(parts)==2 and parts[0]=='build' and '='in parts[1]:
  k,v=parts[1].split('=',1)
  if k in ['vcs.revision','vcs.modified','vcs.time','GOOS','GOARCH','CGO_ENABLED']:settings[k]=v
assert settings['vcs.revision']==m['source_head']
v=(R/'internal/version/VERSION').read_text().strip().removeprefix('v')
assert subprocess.check_output(['git','show',m['source_head']+':internal/version/VERSION'],cwd=R,text=True).strip().removeprefix('v')==v
expected='v'+v+'+'+settings['vcs.revision'][:8]+('.dirty' if settings['vcs.modified']=='true'else'')
m['engine_build_info']=settings;m['expected_core_version']=expected
(B/'manifest.json').write_text(json.dumps(m,indent=2)+'\n')
print(json.dumps({'engine':m['engine'],'expected_core_version':expected,'engine_build_info':settings,'manifest_sha256':hashlib.sha256((B/'manifest.json').read_bytes()).hexdigest()}))
