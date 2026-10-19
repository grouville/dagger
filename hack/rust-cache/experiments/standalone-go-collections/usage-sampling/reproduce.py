"""Run one proposal against its pinned main using identical benchmark files."""
from pathlib import Path
import argparse, json, os, subprocess, tempfile

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--checkout',type=Path,required=True,help='Clean checkout of the pinned upstream main')
p.add_argument('--go',default='go')
p.add_argument('--control',action='store_true')
p.add_argument('--pairs',type=int,default=4)
p.add_argument('--output',type=Path)
a=p.parse_args();here=Path(__file__).resolve().parent
case=json.loads((here/'reproduction.json').read_text())
ref=subprocess.check_output(['git','rev-parse','HEAD'],cwd=a.checkout,text=True).strip()
if ref!=case['base']:p.error('Checkout must be at '+case['base'])
if subprocess.check_output(['git','status','--porcelain'],cwd=a.checkout,text=True).strip():p.error('Checkout must be clean')
key='control' if a.control else 'benefit'
if key not in case:p.error('This fixture has no separate control')
spec=case[key];out=a.output or Path(tempfile.mkdtemp(prefix='dagger-component-'))
out.mkdir(parents=True,exist_ok=True)
env=dict(os.environ,GOMAXPROCS='8',GOTOOLCHAIN='local')
binaries={}
for arm in ['before','candidate']:
 mapping={str(a.checkout.resolve()/dest):str(here/src) for dest,src in spec['overlays'][arm].items()}
 overlay=out/(arm+'.json');overlay.write_text(json.dumps({'Replace':mapping},indent=2)+'\n')
 binary=out/arm;binaries[arm]=binary
 subprocess.run([a.go,'test','-p=2','-c','-overlay='+str(overlay.resolve()),'-o',str(binary.resolve()),spec['package']],cwd=a.checkout,env=env,check=True)
for pair in range(a.pairs):
 for arm in (['before','candidate'] if pair%2==0 else ['candidate','before']):
  cmd=[str(binaries[arm].resolve()),'-test.run=^$','-test.bench='+spec['pattern'],'-test.benchmem','-test.benchtime='+spec['benchtime']]
  result=subprocess.run(cmd,cwd=a.checkout,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
  (out/f'{pair}-{arm}.log').write_text(result.stdout)
  print(f'pair {pair+1}, {arm}\n'+result.stdout,flush=True)
  result.check_returncode()
print('Logs:',out)
