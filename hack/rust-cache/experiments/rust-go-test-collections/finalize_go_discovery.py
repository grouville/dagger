from pathlib import Path
import os
import subprocess

root=Path(__file__).parent;base=root.parent;module=Path('/tmp/dagger-go-package-test-discovery')
original=Path('/tmp/dagger-go-official-collections-oct16/go.dang').read_text()
env=dict(os.environ,RUST_CACHE_BENCH_RUNNER='tcp://127.0.0.1:16276',RUST_CACHE_BENCH_CLI=str(base/'dagger-artifact-list-buffered'),RUST_CACHE_BENCH_COLLECTOR='http://'+(base/'otlp-null-address.txt').read_text().strip()+':43184')
def check(label):
    with (root/(label+'.log')).open('w') as out:r=subprocess.run(['python3',str(base/'local_cli_collector.py'),'check','go-dev:tests-collection-check'],cwd=module,env=env,stdout=out,stderr=subprocess.STDOUT)
    print(label,r.returncode,flush=True);assert r.returncode==0,label
(module/'go.dang').write_text(original)
check('go-discovery-main-unicode')
start=original.index('      # One search over the module tree, matched back to the package\'s files')
end=original.index('        .uniq',start)
replacement='''      # Search immutable files so workspace overlays are visible, while keeping
      # the same matcher and file order as module-wide discovery.
      files
        .reduce(empty) { names, file =>
          names + ws.file("/" + file).search(pattern: testPattern).{{matchedLines}}
            .map { match =>
              match.matchedLines.trimPrefix("func ").split("(").takeFirst(1).join("")
            }
        }
'''
candidate=original[:start]+replacement+original[end:]
pattern=next(line for line in (root/'go-discovery-content-v1.dang').read_text().splitlines() if 'let testPattern: Regexp!' in line)
old_pattern=next(line for line in candidate.splitlines() if 'pattern: `^func (Test' in line)
candidate=candidate.replace(old_pattern,'      pattern: testPattern,',1)
marker='  # Byte-order sort, as Go\'s sort.Strings.'
insertion=candidate.index(marker,candidate.index('  let testMatches('))
candidate=candidate[:insertion]+pattern+'\n\n'+candidate[insertion:]
(module/'go.dang').write_text(candidate)
check('go-discovery-file-search-unicode')
