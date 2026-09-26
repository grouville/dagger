"""Publish only numeric timings, operation classes and verified input hashes."""
from pathlib import Path
import collections,hashlib,json,statistics
lab=Path(__file__).resolve().parent
src=lab/'withfile-v1';out=lab/'withfile-evidence';out.mkdir(exist_ok=True)
def read(p):return json.loads(p.read_text())
def write(n,obj):(out/n).write_text(json.dumps(obj,indent=2)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
rows=read(src/'results.json');assert len(rows)==63 and all(r['correct'] for r in rows)
assert read(src/'restoration.json')['full_fixture_restored']
write('local-samples.json',rows);write('local-summary.json',read(src/'summary.json'))
write('restoration.json',read(src/'restoration.json'))
write('build.json',read(lab/'build-withfile.json'))
proofs={}
for row in rows:
    if not row['profile']:continue
    key=row['flow']+'-'+row['variant'];path=src/f"profile-0-{key}"/'run.wcprof'
    with path.open() as f:
        header=json.loads(next(f));events=[json.loads(l) for l in f]
    ops={r['id']:r for r in events if r['e']=='op'}
    text=lambda r,k:header['strings'][r.get(k,0)]
    builds=[r for r in ops.values() if text(r,'c')=='exec.processRun' and r.get('m') and json.loads(text(r,'m'))[:2]==['go','build']]
    chains=[]
    for op in builds:
        chain=[];seen=set()
        while op:
            assert op['id'] not in seen;seen.add(op['id'])
            chain.append({'kind':op['k'],'class':text(op,'c'),'seconds':(op['d']-op['s'])/1e9})
            op=ops.get(op.get('p'))
        chains.append(chain)
    start=row['started_unix_ns'];end=row['exited_unix_ns'];epoch=header['epoch_unix_nano']
    proof={'cli_seconds':row['seconds'],'profile_sha256':sha(path),'operations':len(ops),'open':len(header.get('open_ops',[])),'dropped':header['dropped_events'],'started_before_cli':sum(epoch+r['s']<start for r in ops.values()),'ended_after_cli':sum(epoch+r['d']>end for r in ops.values()),'go_build_count':len(builds),'go_build_seconds':[(r['d']-r['s'])/1e9 for r in builds],'go_build_parent_chains':chains}
    proofs[key]=proof
write('profile-proof.json',proofs)
assert all(r['open']==r['dropped']==r['started_before_cli']==r['ended_after_cli']==0 for r in proofs.values())
neg=[r for r in rows if r['phase']=='correctness-missing-url'];assert len(neg)==1 and neg[0]['exit_code']!=0
write('correctness.json',{'commands_attempted':len(rows)+1,'validated_commands':len(rows),'successful_commands':sum(r['exit_code']==0 for r in rows),'expected_failure_count':sum(r['expected_failure'] for r in rows),'strict_fresh_http_variants':[r['variant'] for r in rows if r['phase']=='correctness-service' and r['correct']],'missing_url_failed':True,'unaccepted_missing_base_control':read(src/'unaccepted-negative-control.json'),'fixtures_restored':True,'profiles_complete':True})
pairs=[]
for phase,flow,index in sorted({(r['phase'],r['flow'],r['index']) for r in rows if r['phase'] in ('warm','main-edit','test-rename')}):
    pair={r['variant']:r for r in rows if (r['phase'],r['flow'],r['index'])==(phase,flow,index)}
    assert pair['base']['main_sha256']==pair['candidate']['main_sha256']
    assert pair['base']['test_sha256']==pair['candidate']['test_sha256']
    pairs.append({'phase':phase,'flow':flow,'index':index,'base_seconds':pair['base']['seconds'],'candidate_seconds':pair['candidate']['seconds'],'delta_seconds':pair['candidate']['seconds']-pair['base']['seconds'],'same_source':True})
write('paired-deltas.json',pairs)
cloud=lab/'withfile-cloud-v1'
if (cloud/'summary.json').exists():
    cr=read(cloud/'results.json');assert len(cr)==17 and all(r['correct'] for r in cr)
    assert [r for r in cr if r['phase']=='auth-control'][0]['cloud_link_visible']
    assert read(cloud/'restoration.json')['full_fixture_restored']
    write('cloud-samples.json',cr);write('cloud-summary.json',read(cloud/'summary.json'))
    write('cloud-restoration.json',read(cloud/'restoration.json'))
    write('cloud-provenance.json',read(cloud/'provenance.json'))
write('provenance.json',read(src/'provenance.json'))
print(json.dumps({'local_commands':len(rows),'profile_proof':proofs},indent=2))
