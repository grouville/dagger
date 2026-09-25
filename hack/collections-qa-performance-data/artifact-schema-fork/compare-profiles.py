from pathlib import Path
import subprocess,json,os
os.environ.pop('SSH_AUTH_SOCK',None)
base=Path('/tmp/collections-perf/discovery-next')
for label,engine,port in [('control','dagger-engine.collections-tsx-node-cache',6145),('candidate','dagger-engine.collections-artifact-schema-fork',6146)]:
 dest=base/(label+'-wcprof')
 p=subprocess.run(['python3','/home/dagger/dag/hack/bench-artifact-discovery.py','--runs','1','--warmups','0','--output',str(dest),'--wcprof-url',f'http://127.0.0.1:{port}','--expect-stdout','/home/dagger/dag/hack/collections-qa-performance-data/expected-checks.txt','--','/tmp/collections-perf/committed/dagger','--engine','container://'+engine,'check','-l','--all'],cwd='/tmp/collections-perf/normal-baseline/greetings-split',capture_output=True,text=True)
 (dest/'driver.log').write_text(p.stdout+p.stderr);p.check_returncode()
 with (dest/'analysis.txt').open('w') as out:subprocess.run(['/tmp/wcprof-analyze','-top','35',str(dest/'runs.wcprof')],stdout=out,check=True)
 print(label,json.loads((dest/'results.json').read_text())['median_seconds'],flush=True)
