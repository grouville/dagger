from pathlib import Path
import json,os,subprocess

base=Path('/tmp/rust-cache-sipsma-review')
root=base/'no-git-workspace-default-path-directory'
excluded={'DAGGER_SESSION_PORT','DAGGER_SESSION_TOKEN','SSH_AUTH_SOCK','DAGGER_CLOUD_TOKEN','DAGGER_CLOUD_URL','DAGGER_ENGINE','DAGGER_CLOUD_ENGINE','HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','http_proxy','https_proxy','all_proxy'}
env={k:v for k,v in os.environ.items() if k not in excluded and not k.startswith('OTEL_EXPORTER_')}
env.update(DAGGER_CLOUD_URL='http://'+(base/'otlp-null-address.txt').read_text().strip()+':43184',
           DAGGER_CLOUD_TOKEN='local-benchmark-token',NO_PROXY='*',
           _EXPERIMENTAL_DAGGER_RUNNER_HOST='tcp://127.0.0.1:16276',
           XDG_CONFIG_HOME='/tmp/rust-cache-oct13-filter/local-client-config')
rows={}
for name,expected in [('no-git',Path('/tmp')),('git',root/'git')]:
    project=root/name
    git=subprocess.run(['git','-C',str(project),'rev-parse','--show-toplevel'],text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    command=[str(base/'dagger-artifact-list-buffered'),'workspace','root']
    result=subprocess.run(command,cwd=project,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    rows[name]=dict(cwd=str(project),git_returncode=git.returncode,git_stdout=git.stdout,git_stderr=git.stderr,
                    command=command,returncode=result.returncode,stdout=result.stdout,stderr=result.stderr)
    assert result.returncode==0,(name,result.stderr)
    assert result.stdout.strip()==str(expected),(name,result.stdout,expected)
marker=Path('/tmp/.git')
rows['ambient_marker']=dict(path=str(marker),exists=marker.exists(),is_directory=marker.is_dir())
assert marker.exists()
(root/'boundary-provenance.json').write_text(json.dumps(rows,indent=2)+'\n')
print('PASS Dagger uses /tmp without a local marker and the project root with one',flush=True)
