from pathlib import Path
import os,subprocess,json,concurrent.futures,urllib.request,time
os.environ.pop('SSH_AUTH_SOCK',None)
b=Path('/tmp/collections-perf/warm-next');dest=b/'baseline-profile';dest.mkdir(exist_ok=True)
cli='/tmp/collections-perf/committed/dagger';engine='container://dagger-engine.collections-go-import-quiet-1';ws='/tmp/collections-perf/normal-baseline/greetings-split';url='http://127.0.0.1:6128'
# Warm the existing engine before starting the CPU window.
p=subprocess.run(['python3','/home/dagger/dag/hack/bench-artifact-discovery.py','--runs','2','--warmups','1','--output',str(b/'baseline-warm'),'--expect-stdout','/home/dagger/dag/hack/collections-qa-performance-data/expected-checks.txt','--',cli,'--engine',engine,'check','-l','--all'],cwd=ws,capture_output=True,text=True)
(b/'baseline-warm.log').write_text(p.stdout+p.stderr);p.check_returncode()
def profile():
 with urllib.request.urlopen(url+'/debug/pprof/profile?seconds=10',timeout=30) as r:(dest/'engine.pprof').write_bytes(r.read())
with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
 f=pool.submit(profile)
 time.sleep(.2)
 p=subprocess.run(['python3','/home/dagger/dag/hack/bench-artifact-discovery.py','--runs','1','--warmups','0','--output',str(dest),'--wcprof-url',url,'--expect-stdout','/home/dagger/dag/hack/collections-qa-performance-data/expected-checks.txt','--',cli,'--engine',engine,'check','-l','--all'],cwd=ws,capture_output=True,text=True)
 (dest/'driver.log').write_text(p.stdout+p.stderr);p.check_returncode();f.result()
with (dest/'analysis.txt').open('w') as out:subprocess.run(['/tmp/wcprof-analyze','-top','30',str(dest/'runs.wcprof')],stdout=out,check=True)
print(json.loads((dest/'results.json').read_text())['median_seconds'])
