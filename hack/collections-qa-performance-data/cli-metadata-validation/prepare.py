from pathlib import Path
import json,difflib
HERE=Path(__file__).resolve().parent;REPO=Path('/home/dagger/dag');source=REPO/'engine/server/session_workspaces.go';text=source.read_text();(HERE/'session_workspaces.original.go').write_text(text)
text=text.replace('// only full-schema demand is currentTypeDefs, the scope replaces its','// only full-schema demand is a currentTypeDefs projection, the scope replaces its')
old='if field == "currentTypeDefs" {';assert text.count(old)==1;text=text.replace(old,'if field == "currentTypeDefs" || field == "__currentTypeDefsJSON" {',1)
old='\t\t\t"currentTypeDefs",';assert text.count(old)==1;text=text.replace(old,old+'\n\t\t\t"__currentTypeDefsJSON",',1)
(HERE/'session_workspaces.go').write_text(text)
for name,variant in [('baseline','session_workspaces.original.go'),('candidate','session_workspaces.go')]:
 overlay={'Replace':{str(source):str(HERE/variant),str(REPO/'engine/server/typedef_json_demand_test.go'):str(HERE/'typedef_json_demand_test.go')}}
 (HERE/(name+'-overlay.json')).write_text(json.dumps(overlay,indent=2)+'\n')
