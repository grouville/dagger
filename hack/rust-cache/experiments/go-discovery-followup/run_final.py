from pathlib import Path
import json,subprocess,sys,time
root=Path(__file__).parent
jobs=[('metadata-final','measure_real_metadata.py',['--pairs','2','--seed','2026101645']),('collections-final','measure_collections.py',['--sizes','1','16','64','--pairs','4','--seed','2026101646']),('many-files-final','measure_many_files.py',['--sizes','1','--pairs','4','--seed','2026101647'])]
rows=[]
for label,script,args in jobs:
    command=[sys.executable,str(root/script),'--output',str(root/label)]+args
    tick=time.time()
    print('starting',label,flush=True)
    with (root/(label+'.log')).open('w') as out:result=subprocess.run(command,stdout=out,stderr=subprocess.STDOUT)
    rows.append(dict(label=label,start=tick,end=time.time(),exit_code=result.returncode,command=command))
    (root/'final-jobs.json').write_text(json.dumps(rows,indent=2)+'\n')
    print('finished',label,result.returncode,flush=True)
    assert result.returncode==0,label
