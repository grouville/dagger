from pathlib import Path
import json,subprocess,time
root=Path(__file__).parent
start=time.monotonic()
while True:
    result=root/'correctness.json'
    if result.exists():
        checks=json.loads(result.read_text())
        assert all(c['exit_code']==0 for c in checks),checks
        if len(checks)==4:break
    assert time.monotonic()-start<900,'Correctness checks did not complete.'
    time.sleep(1)
print('Focused checks passed; starting full listing comparison.',flush=True)
r=subprocess.run(['python3',str(root/'measure_listing.py'),'--output',str(root/'listing-paired'),'--pairs','2'])
raise SystemExit(r.returncode)
