from pathlib import Path
import json,subprocess
from benchmark_helpers import engine_info,run
out=Path('/tmp/go-collection-upstream-review-oct19')
engine=engine_info('dagger-collection-standalone-main-oct19','tcp://127.0.0.1:16310','http://127.0.0.1:16130')
rows=[]
for arm,module in [('before',Path('/tmp/go-collection-clean-go-main')),('candidate',out/'go-package-workspace')]:
 root=out/'scoped-module-path-probe'/arm;root.mkdir(parents=True)
 subprocess.run(['git','init','--quiet',str(root)],check=True)
 package=root/'module[1]';package.mkdir()
 (package/'go.mod').write_text('module example.com/validmodule\n\ngo 1.26.6\n')
 (package/'value_test.go').write_text('package fixture\nimport "testing"\nfunc TestModulePath(t *testing.T) {}\n')
 (root/'dagger.toml').write_text('[modules.go]\nsource = "'+str(module)+'"\n[modules.go.settings]\nversion = "1.26.6"\ntest = ["**"]\n')
 metrics,text,log=run('scoped-module-path-'+arm,root,['check','--module','go','--check','test','--list','--all'],engine)
 names=[tuple(line.split()[1:3]) for line in text.splitlines() if line.startswith('go ')]
 record=dict(arm=arm,names=names,expected_names=[['module[1]','TestModulePath']],correct=names==[('module[1]','TestModulePath')],log=log,**metrics)
 rows.append(record);(out/'scoped-module-path-probe.json').write_text(json.dumps(rows,indent=2)+'\n');print(json.dumps(record),flush=True)
