from pathlib import Path
import json
from benchmark_helpers import engine_info,run
out=Path('/tmp/go-collection-upstream-review-oct19')
new=json.loads((out/'workspace-overlay-engine.json').read_text())
engines={'main':engine_info('dagger-collection-standalone-main-oct19','tcp://127.0.0.1:16310','http://127.0.0.1:16130'),'fix':engine_info(new['name'],new['runner'],new['debug'])}
rows=json.loads((out/'scoped-package-checks.json').read_text())
for label,module,check,engine,positive in [
 ('main-filenames','go-package-main-probe','go-dev:package-search-filenames-check','main',True),
 ('scoped-filenames','go-package-workspace','go-dev:package-search-filenames-check','main',True),
 ('scoped-new-package-main','go-package-workspace','go-dev:package-search-overlay-check','main',False),
 ('scoped-new-package-fix','go-package-workspace','go-dev:package-search-overlay-check','fix',True),
 ('scoped-collection-execution','go-package-workspace','go-dev:tests-collection-check','main',True)]:
 metrics,text,log=run(label,out/module,['check',check],engines[engine]);row=dict(label=label,module=module,engine=engine,expected_success=positive,log=log,**metrics);rows.append(row)
 (out/'scoped-package-checks.json').write_text(json.dumps(rows,indent=2)+'\n');print(json.dumps(row),flush=True)
 if positive:assert metrics['cleanup_successful'],Path(log).read_text()[-2000:]
 else:
  error=Path(log).read_text();assert metrics['exit_code']!=0 and ('literal filename tests' in error if label.startswith('file-probe') else 'No such file or directory' in error),error[-2000:]
