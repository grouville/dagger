from pathlib import Path
import json,subprocess,time
root=Path(__file__).parent
jobs=['verify_after_cohort.py','analyze_profile.py','analyze_windows.py','locate.py']
rows=[]
for name in jobs:
 command=['python3',str(root/name)];started=time.monotonic()
 with (root/(name.removesuffix('.py')+'-driver.log')).open('w') as out:r=subprocess.run(command,stdout=out,stderr=subprocess.STDOUT)
 rows.append(dict(command=command,exit_code=r.returncode,seconds=time.monotonic()-started));(root/'post-capture-validation.json').write_text(json.dumps(rows,indent=2)+'\n');print(name,r.returncode,flush=True)
 assert r.returncode==0,name
