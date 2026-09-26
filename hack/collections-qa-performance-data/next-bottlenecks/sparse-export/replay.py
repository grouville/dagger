from pathlib import Path
import json, os, subprocess, time
lab=Path(__file__).resolve().parent
out=lab/'no-git-replay';out.mkdir(exist_ok=False)
config=out/'empty-config';config.mkdir(mode=0o700)
ws=Path('/tmp/collections-perf/cli-key-scaling/vertical-local-v2/workspace')
env=dict(os.environ)
for key in list(env):
    if key.startswith(('OTEL_','DAGGER_SESSION_','DAGGER_CLOUD_')) or key in ('SSH_AUTH_SOCK','CPUPROFILE','DAGGER_CONFIG','DAGGER_PERF_TIMELINE','TRACEPARENT','TRACESTATE','BAGGAGE','_EXPERIMENTAL_DAGGER_CACHE_CONFIG','_EXPERIMENTAL_DAGGER_CACHE_IMPORT_CONFIG','_EXPERIMENTAL_DAGGER_CACHE_EXPORT_CONFIG','_EXPERIMENTAL_DAGGER_CHECKS_SCALE_OUT'):env.pop(key,None)
env.update(XDG_CONFIG_HOME=str(config),DO_NOT_TRACK='1',DAGGER_NO_UPDATE_CHECK='1')
marker='sparse-export-candidate-replay\n';(ws/'input.txt').write_text(marker)
cmd=[str(lab/'dagger-key-and-disk'),'--engine','container://dagger-engine.collections-disk-abba-2','-y','generate','render']
start=time.monotonic();visible=None
with (out/'stdout.txt').open('wb') as stdout,(out/'stderr.txt').open('wb') as stderr:
    proc=subprocess.Popen(cmd,cwd=ws,env=env,stdout=stdout,stderr=stderr)
    try:
        while time.monotonic()-start<90:
            try:
                if (ws/'generated.txt').read_text()==marker:visible=time.monotonic()-start;break
            except FileNotFoundError:pass
            if proc.poll() is not None:break
            time.sleep(.005)
        status=proc.wait(timeout=90)
    finally:
        if proc.poll() is None:proc.terminate();proc.wait(timeout=15)
row={'command':cmd,'seconds':time.monotonic()-start,'file_visible_seconds':visible,'exit_code':status,'contents_correct':(ws/'generated.txt').read_text()==marker,'telemetry_mode':'local-only audited empty config; no Cloud','baseline':'previous ~61s failure after writing file; deliberately not rerun across /tmp'}
(out/'result.json').write_text(json.dumps(row,indent=2)+'\n');print(json.dumps(row))
assert status==0 and row['contents_correct']
