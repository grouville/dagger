from pathlib import Path
import subprocess
b=Path('/tmp/rust-cache-sipsma-review')
for label,variant in [('prepare-before','before'),('prepare-after','after'),('pair0-before','before'),('pair0-after','after'),('pair1-after','after'),('pair1-before','before')]:
 module='/tmp/dagger-rust-profile-'+('compiler-helper' if variant=='before' else 'worker-request-current')
 root='worker-request-profile-'+label
 with (b/(root+'-driver.log')).open('w') as log:
  process=subprocess.run(['python3',str(b/'profile_compiler_helper.py'),'--module',module,'--root',root,'--sizes','1026','--rounds','1'],stdout=log,stderr=subprocess.STDOUT)
 assert process.returncode==0,label
 print('PASS',label,flush=True)
