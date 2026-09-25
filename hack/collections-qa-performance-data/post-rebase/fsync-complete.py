from pathlib import Path
import sys,subprocess,time,os,signal,json,shutil
sys.path.insert(0,'/tmp/collections-perf/post-rebase-io')
import run as lab
name='dagger-engine.collections-complete-fsync-2';port=6169
libdir=lab.B/'strace-tools';libdir.mkdir(exist_ok=True)
for p in ['/usr/bin/strace','/lib/x86_64-linux-gnu/libunwind-ptrace.so.0','/lib/x86_64-linux-gnu/libunwind-x86_64.so.8','/lib/x86_64-linux-gnu/libc.so.6','/lib/x86_64-linux-gnu/liblzma.so.5','/lib/x86_64-linux-gnu/libunwind.so.8','/lib64/ld-linux-x86-64.so.2']:
 shutil.copyfile(p,libdir/Path(p).name)
for n in ['strace','ld-linux-x86-64.so.2']:
 (libdir/n).chmod(0o755)
trace=None
try:
 lab.start(name,port,image='localhost/dagger-engine.collections-main-io:baseline')
 lab.run(['docker','cp',str(libdir),name+':/tmp/strace-tools'])
 proc=lab.run(['docker','exec',name,'sh','-c','for p in /proc/[0-9]*/comm; do if [ "$(cat "$p")" = dagger-engine ]; then echo "$p"; fi; done']).splitlines()[0].split('/')[2]
 trace=subprocess.Popen(['docker','exec',name,'/tmp/strace-tools/ld-linux-x86-64.so.2','--library-path','/tmp/strace-tools','/tmp/strace-tools/strace','-f','-ttt','-T','-yy','-e','trace=fsync,fdatasync','-p',proc,'-o','/tmp/fsync.strace'],stdout=(lab.B/'strace-attach-stdout.txt').open('w'),stderr=(lab.B/'strace-attach.log').open('w'))
 for _ in range(30):
  if trace.poll() is not None:raise RuntimeError('strace exited '+str(trace.returncode))
  if subprocess.run(['docker','exec',name,'test','-f','/tmp/fsync.strace']).returncode==0:break
  time.sleep(.1)
 else:raise RuntimeError('strace output file missing')
 lab.measure(name,port,Path('/tmp/collections-perf/normal-baseline/greetings-split'),'cold',profile=True)
finally:
 try:
  subprocess.run(['docker','cp',name+':/tmp/fsync.strace',str(lab.B/'complete-cold-fsync.strace')],check=True)
 finally:
  subprocess.run(['docker','stop','--timeout','30',name],capture_output=True)
  if trace is not None:trace.wait(timeout=10)
