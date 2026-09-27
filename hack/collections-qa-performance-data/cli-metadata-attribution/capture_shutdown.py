"""Read one verified stopped task engine's retained logs. No CLI or Cloud calls."""
from pathlib import Path
from datetime import datetime,timezone
import json,os,re,shlex,subprocess,hashlib,argparse
p=argparse.ArgumentParser();p.add_argument('--capture',action='store_true');a=p.parse_args()
ROOT=Path('/tmp/collections-perf/cli-metadata-runtime-v1/cloud-v1');OUT=Path(__file__).resolve().parent/'shutdown'
if not a.capture: print(json.dumps({'execute':False,'cloud_commands':0,'source':'one stopped task-owned engine log window'}));raise SystemExit
os.umask(0o077);assert not OUT.exists();OUT.mkdir(mode=0o700)
provenance=json.loads((ROOT/'provenance.json').read_text());rows=json.loads((ROOT/'results.json').read_text());item=provenance['original_engine']
for i,r in enumerate(rows):r['ordinal']=i
info=json.loads(subprocess.check_output(['docker','inspect',item['name']]))[0]
assert info['Id']==item['id'] and info['Config']['Labels'].get('dagger.perf.owner')=='collections-lazy-core-runtime-v1'
assert not info['State']['Running']
start=min(r['started_unix_ns']for r in rows);end=max(r['exited_unix_ns']for r in rows)+5_000_000_000
iso=lambda ns:datetime.fromtimestamp(ns/1e9,tz=timezone.utc).isoformat()
r=subprocess.run(['docker','logs','--timestamps','--since',iso(start),'--until',iso(end),item['name']],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,check=True)
(OUT/'engine.private.log').write_bytes(r.stdout)
units={'ns':1e-6,'us':1e-3,'µs':1e-3,'μs':1e-3,'ms':1,'s':1000,'m':60000,'h':3600000}
def millis(s):
 parts=re.findall(r'(\d+(?:\.\d+)?)(ns|us|µs|μs|ms|s|m|h)',s);assert parts and ''.join(a+b for a,b in parts)==s
 return sum(float(v)*units[u]for v,u in parts)
def epoch(line):
 m=re.fullmatch(r'(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(?:\.(\d+))?Z',line.split(' ',1)[0])
 if not m:return None
 return int(datetime.fromisoformat(m[1]).replace(tzinfo=timezone.utc).timestamp())*1_000_000_000+int((m[2]or'').ljust(9,'0')[:9])
allowed={'flush workspace locks','flush session Cloud telemetry','stop session services','flush session telemetry'};raw=[]
for line in r.stdout.decode(errors='replace').splitlines():
 if not any(x in line for x in ['shutdown drain phase done','client shutdown done','session telemetry flush','session telemetry shutdown']):continue
 timestamp=epoch(line)
 if timestamp is None:continue
 try:tokens=shlex.split(re.sub(r'\x1b\[[0-9;]*m','',line))
 except ValueError:continue
 fields={k:v for token in tokens if '='in token for k,v in[token.split('=',1)]}
 if 'shutdown drain phase done'in line:
  phase=fields.get('phase')
  if phase not in allowed:continue
 elif 'client shutdown done'in line:phase='shutdown handler total'
 elif 'session telemetry shutdown'in line:phase='final session telemetry shutdown'
 elif 'session telemetry flush'in line:phase='session telemetry flush detail'
 else:continue
 if 'duration'not in fields:continue
 matching=[row for row in rows if row['started_unix_ns']<=timestamp<=row['exited_unix_ns']];assert len(matching)<=1
 raw.append(dict(timestamp=timestamp,fields=fields,phase=phase,matching=matching[0]if matching else None))
by_session={}
for e in raw:
 if e['matching']is not None and e['fields'].get('isMainClient')=='true':
  sid=e['fields'].get('sessionID')
  if sid:
   old=by_session.setdefault(sid,e['matching']);assert old['ordinal']==e['matching']['ordinal']
safe=[]
for e in raw:
 fields=e['fields'];sr=by_session.get(fields.get('sessionID'));row=sr or e['matching']
 if row is None:continue
 record=dict(command_ordinal=row['ordinal'],variant=row['variant'],flow=row['flow'],command_phase=row['phase'],command_index=row['index'],production=row['production'],client_is_main={'true':True,'false':False}.get(fields.get('isMainClient')),phase=e['phase'],duration_ms=millis(fields['duration']),within_command=row['started_unix_ns']<=e['timestamp']<=row['exited_unix_ns'],associated_via_main_session=sr is not None and(e['matching']is None or sr['ordinal']!=e['matching']['ordinal']),end_from_command_start_ms=(e['timestamp']-row['started_unix_ns'])/1e6,end_relative_to_command_exit_ms=(e['timestamp']-row['exited_unix_ns'])/1e6)
 if e['phase']in['session telemetry flush detail','final session telemetry shutdown']:record['signal_duration_ms']={k:millis(fields[k])for k in['traces','logs','metrics']if k in fields}
 safe.append(record)
assert any(e['client_is_main']and e['phase']=='flush session Cloud telemetry'for e in safe),'No supported numeric records'
result=dict(rows=safe,capture=dict(raw_sha256=hashlib.sha256(r.stdout).hexdigest(),raw_bytes=len(r.stdout)),new_cloud_commands=0,limits=['Only allowlisted labels and numeric durations are exported. Raw logs stay private.','Docker timestamps bracket logged phase completion. Phase durations come from engine clocks.','Cloud flush includes export completion and token-refresh gate, not measured network RTT or server processing.','Session-wide background teardown may extend past CLI exit. Association uses private session keys in memory only.'])
(OUT/'numeric-phases.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({'numeric_records':len(safe),'main_cloud_flushes':sum(bool(e['client_is_main'])and e['phase']=='flush session Cloud telemetry'for e in safe),'raw_published':False}))
