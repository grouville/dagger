from pathlib import Path
import sys,subprocess,time,urllib.request,json
sys.path.insert(0,'/tmp/collections-perf/post-rebase-io')
import run as lab
ws=Path('/tmp/collections-perf/normal-baseline/greetings-split');source=ws/'main_test.go';original=source.read_bytes();want=lab.WANT
for suffix in [3,2]:
 name=f'dagger-engine.collections-disk-abba-{suffix}';port=6170+suffix
 try:
  lab.run(['docker','start',name])
  for i in range(100):
   try:urllib.request.urlopen(f'http://127.0.0.1:{port}/debug/pprof/',timeout=1).close();break
   except OSError:time.sleep(.1)
  lab.measure(name,port,ws,'edit-warmup')
  source.write_bytes(original+b'\n// Performance check: source changed, discovery keys unchanged.\n')
  lab.measure(name,port,ws,'edit-comment')
  source.write_bytes(source.read_bytes().replace(b'func TestFormatResponse(',b'func TestFormatResponze('))
  lab.WANT=want.replace(b'TestFormatResponse',b'TestFormatResponze')
  lab.measure(name,port,ws,'edit-rename')
  source.write_bytes(original);lab.WANT=want
  lab.measure(name,port,ws,'edit-restore')
 finally:
  source.write_bytes(original);lab.WANT=want
  subprocess.run(['docker','stop','--timeout','30',name],capture_output=True)
