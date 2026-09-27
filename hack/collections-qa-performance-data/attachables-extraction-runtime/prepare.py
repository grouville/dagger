from pathlib import Path
import json,hashlib,difflib,shutil
H=Path(__file__).resolve().parent;P=Path('/tmp/collections-perf/split-init-runtime-v1');E=Path('/tmp/collections-perf/attachables-extraction-v1')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
s=(P/'runtime.py').read_text();original=s
start=s.index('"""');end=s.index('"""',start+3)+3
s=s[:start]+'''"""Prepared attachables extraction LOCAL correctness only:10 calls, no profiles.

The same ordinary ec6 engine serves both arms; only the original-style heavy
/.init binary changes. No light PID1 or separate helper mount is introduced.
Prior nested SDK flow/golden/ownership scaffold retained; no latency claim.
"""'''+s[end:]
s=s.replace('csv, io','csv, io, tomllib')
s=s.replace("OWNER='collections-split-init-v1'","OWNER='collections-attachables-extraction-v1'")
s=s.replace("PARENT_ENGINE='2c005dfc7f2d7ad65ec0ed0f28c27aad1af1ea47a26602cc0ad7740c11acf62f'","PARENT_ENGINE='ec6a2d88ca54b1c12fc81c7381538e23d100fece04d703daac0b17dcf3d3ebc1'")
s=s.replace("MANIFEST=Path('/tmp/collections-perf/split-init-prototype-v1/build-results-v1/runtime-builds.json')","MANIFEST=Path('/tmp/collections-perf/attachables-extraction-v1/build-results-v1/runtime-builds.json')")
s=s.replace('CAPS={"smoke":10,"measure":36}','CAPS={"smoke":10}')
a=s.index('  print(json.dumps(',s.index(' if not a.run:'));b=s.index(';return',a)+len(';return')
s=s[:a]+"  print(json.dumps({'execute':False,'local_commands_cap':10,'cloud_commands':0,'profile_commands':0,'scope':'Go/TypeScript/Python actual nested reads, fresh selected Go check and unique ordinary exec per arm; correctness only','engine_sha256':PARENT_ENGINE,'only_variant':'heavy init binary; no split PID1','manifest_required':str(FROZEN_MANIFEST)}));return"+s[b:]
a=s.index(" recipe=json.loads(Path(manifest['recipe_path'])");b=s.index(" assert x.sha(CLI)",a)
s=s[:a]+''' recipe_path=Path('/tmp/collections-perf/attachables-extraction-v1/build-recipe.json')
 recipe=json.loads(recipe_path.read_text());assert x.sha(recipe_path)==manifest['recipe_sha256']
 engine={'path':'/tmp/collections-perf/catalog-next-levers-v1/git-http/builds/engine-diagnostic','sha256':PARENT_ENGINE,'exit_code':0}
 engines={v:engine for v in ('baseline','candidate')}
 helpers=manifest['builds'];assert set(helpers)=={'baseline','candidate'}
 for artifact in [engine,*helpers.values()]:assert artifact['exit_code']==0 and x.sha(artifact['path'])==artifact['sha256']
'''+s[b:]
s=s.replace("expected_version=recipe['expected_core_version'].encode()","expected_version=inputs['expected_core_version'].encode()")
s=s.replace(" assert manifest['source_head']=='0d1c32e29f2f31cdb95f0b5f17f7daed7305bc87'"," assert recipe['source_head']=='e6e723145e914680b9daea080046c55eb6ccc233'")
a=s.index(" if a.stage=='measure':");b=s.index(" original=json.loads",a);s=s[:a]+s[b:]
needle=" originals={native/n:"
pos=s.index(needle)
s=s[:pos]+''' for module in ('backend','frontend'):
  cfg=tomllib.loads((app/'.dagger/modules'/module/'dagger-module.toml').read_text())
  assert cfg['disableDefaultFunctionCaching'] is True
 assert json.loads((HERE/'python-template/module/dagger.json').read_text())['disableDefaultFunctionCaching'] is True
'''+s[pos:]
s=s.replace("name='dagger-engine.collections-split-init-'","name='dagger-engine.collections-attachables-' ")
s=s.replace("'helpers_both_arms':helpers","'helper_variants':helpers")
s=s.replace("Both common heavy and lite helpers installed identically in both arms. Engines differ only split PID1/helper dispatch and mounts. Smoke is correctness/setup, not timed comparison; first Python SDK setup is visible and counted. Measurement uses fully primed ABBA engine blocks on the retained volume. Each app-comment and generator input has never-seen bytes.","Same ordinary engine and retained volume in both arms; only original-style heavy init is replaced. No split PID1. Go/TS/Python modules disable default function caching, selected Go test and ordinary exec use fresh input. Correctness/setup only, including first Python setup if any; no timing claim.")
s=s.replace("'scope':'No Cloud/fresh-volume cold/service-up claim. Actual SDK runtime reads, changed selected-test body and unique ordinary exec are explicit smoke gates. Native generation is not SDK code generation.'","'scope':'No Cloud/profile/cold/performance claim; ten actual SDK/check/exec correctness calls only.'")
old="  x.capture(['docker','cp',engine['path'],name+':/usr/local/bin/dagger-engine']);item['sha256']=engine['sha256']\n  for destination,helper in helpers.items():x.capture(['docker','cp',helper['path'],name+':'+destination])"
new="  x.capture(['docker','cp',engine['path'],name+':/usr/local/bin/dagger-engine']);item['sha256']=engine['sha256']\n  helper=helpers[variant]\n  x.capture(['docker','cp',helper['path'],name+':/usr/local/bin/dagger-init'])"
assert old in s;s=s.replace(old,new)
s=s.replace("  for destination,helper in helpers.items():assert x.capture(['docker','exec',name,'sha256sum',destination]).split()[0]==helper['sha256']","  assert x.capture(['docker','exec',name,'sha256sum','/usr/local/bin/dagger-init']).split()[0]==helper['sha256']")
s=s.replace("'split-init-selected-","'attachables-selected-").replace("'split-init-exec-","'attachables-exec-")
a=s.index("   init_hash=helpers[");b=s.index("   encoded=io.StringIO()",a)
s=s[:a]+'''   init_hash=helpers[variant]['sha256']
   shell='set -eu; test -x /.init; test "$(sha256sum /.init | cut -d " " -f1)" = "$2"; test ! -e /.dagger-session; printf %s "$1"'
   logical_args=['sh','-c',shell,'attachables-smoke',contents.decode(),init_hash]
'''+s[b:]
a=s.index("  if a.stage=='smoke':\n   for block,");b=s.index('\n finally:',a)
s=s[:a]+'''  for block,variant in enumerate(('baseline','candidate')):
   install_engine(variant,block)
   for flow in ('go-read','ts-read','ordinary-exec','greetings-check','python-read'):
    run(variant,flow,'sdk-correctness-and-setup',block,profile=False)
  x.write(out/'dispatch-policy.json',{'profiles':0,'go_typescript_python_default_function_caching_disabled':True,'selected_test_unique_body_per_variant':True,'ordinary_exec_unique_argv_per_variant':True,'ordinary_exec_verified_mounted_init_sha256':True,'extra_helper_mount_absent':True,'scope':'Operational correctness gate, not process-count or performance measurement'})
'''+s[b:]
(H/'runtime.py').write_text(s)
(H/'runtime-vs-reviewed.diff').write_text(''.join(difflib.unified_diff(original.splitlines(True),s.splitlines(True),fromfile='split-init-runtime-v1/runtime.py@53c482',tofile='attachables-extraction-runtime-v1/runtime.py')))
shutil.copyfile(E/'build-results-v1/runtime-builds.json',H/'frozen-runtime-manifest.json')
inputs=json.loads((P/'frozen-inputs.json').read_text());inputs.pop('engine_manifest_sha256',None);inputs['prior_fixture_inputs_sha256']=sha(P/'frozen-inputs.json');inputs['engine_sha256']='ec6a2d88ca54b1c12fc81c7381538e23d100fece04d703daac0b17dcf3d3ebc1'
(H/'frozen-inputs.json').write_text(json.dumps(inputs,indent=2)+'\n')
shutil.copyfile(P/'fixture-inventory.json',H/'fixture-inventory.json')
if not (H/'python-template').exists():shutil.copytree(P/'python-template',H/'python-template')
compile(s,str(H/'runtime.py'),'exec')
print(json.dumps({'driver_sha256':sha(H/'runtime.py'),'scope':'prepared only, 10 local correctness calls, zero profiles/Cloud'}))
