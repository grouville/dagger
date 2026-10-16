from pathlib import Path
import json,os,subprocess

base=Path('/tmp/rust-cache-sipsma-review')
root=base/'no-git-workspace-default-path-directory'
root.mkdir(exist_ok=False)
module=Path('/tmp/rust-no-git-default-path-directory-probe-module')
module.mkdir(exist_ok=False)
(module/'dagger-module.toml').write_text('name = "root-probe"\nengineVersion = "v1.0.0-0"\n[runtime]\nsource = "dang"\n')
(module/'main.dang').write_text('''type RootProbe {
  check(source: Directory! @defaultPath(path: "/marker-dir")): Void @check {
    assert("The marker must come from the calling workspace") {
      source.file("marker.txt").contents == "workspace marker\\n"
    }
    null
  }
}
''')
subprocess.run(['git','init','--quiet',str(module)],check=True)
excluded={'DAGGER_SESSION_PORT','DAGGER_SESSION_TOKEN','SSH_AUTH_SOCK','DAGGER_CLOUD_TOKEN','DAGGER_CLOUD_URL','DAGGER_ENGINE','DAGGER_CLOUD_ENGINE','HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','http_proxy','https_proxy','all_proxy'}
env={k:v for k,v in os.environ.items() if k not in excluded and not k.startswith('OTEL_EXPORTER_')}
env.update(DAGGER_CLOUD_URL='http://'+(base/'otlp-null-address.txt').read_text().strip()+':43184',
           DAGGER_CLOUD_TOKEN='local-benchmark-token',NO_PROXY='*',
           _EXPERIMENTAL_DAGGER_RUNNER_HOST='tcp://127.0.0.1:16276',
           XDG_CONFIG_HOME='/tmp/rust-cache-oct13-filter/local-client-config')
results=[]
for name in ['no-git','git']:
    project=root/name
    project.mkdir()
    (project/'marker-dir').mkdir()
    (project/'marker-dir/marker.txt').write_text('workspace marker\n')
    (project/'dagger.toml').write_text('[modules.probe]\nsource = '+json.dumps(str(module))+'\n')
    if name=='git':subprocess.run(['git','init','--quiet',str(project)],check=True)
    command=[str(base/'dagger-artifact-list-buffered'),'check','probe:check']
    with (root/(name+'.log')).open('w') as output:
        result=subprocess.run(command,cwd=project,env=env,stdout=output,stderr=subprocess.STDOUT)
    rows=(root/(name+'.log')).read_text().splitlines()
    detail=[row[:500] for row in rows if any(term in row for term in ['Host.file(', 'Host.directory(', 'ERROR', 'Error:', 'error:', 'no such file'])]
    results.append(dict(name=name,project=str(project),git_boundary=name=='git',command=command,returncode=result.returncode,details=detail[:12]))
    (root/'results.json').write_text(json.dumps(results,indent=2)+'\n')
    print(name,'returncode',result.returncode,detail[:4],flush=True)
