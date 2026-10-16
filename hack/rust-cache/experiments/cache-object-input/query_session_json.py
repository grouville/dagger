import base64,json,os,sys,urllib.request
from pathlib import Path
payload=json.dumps({'query':Path(sys.argv[1]).read_text()}).encode()
auth=base64.b64encode((os.environ['DAGGER_SESSION_TOKEN']+':').encode()).decode()
req=urllib.request.Request('http://127.0.0.1:'+os.environ['DAGGER_SESSION_PORT']+'/query',data=payload,headers={'Content-Type':'application/json','Authorization':'Basic '+auth})
with urllib.request.urlopen(req,timeout=300) as response:value=json.load(response)
if value.get('errors'):raise RuntimeError(value['errors'])
Path(sys.argv[2]).write_text(json.dumps(value['data'])+'\n')
