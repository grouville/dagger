from pathlib import Path
import os
import subprocess

root = Path(__file__).parent
capture = root / 'capture'
go = '/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go'
engine = str(root / 'dagger-engine')
commands = {
    'compaction-window-cpu.txt': ['-top', '-cum', '-nodecount=40', engine,
        str(capture / 'engine-cpu-008.pprof'), str(capture / 'engine-cpu-009.pprof')],
    'mutex-delta.txt': ['-top', '-cum', '-nodecount=35', '-base',
        str(capture / 'mutex-before.pprof'), engine, str(capture / 'mutex-after.pprof')],
    'compaction-allocation-lines.txt': ['-top', '-alloc_space', '-lines', '-focus',
        'compactEqClassesModeLocked', '-nodecount=45', '-base',
        str(capture / 'engine-allocs-before.pprof'), engine, str(capture / 'engine-allocs-after.pprof')],
    'prune-mutex-delta.txt': ['-top', '-cum', '-nodecount=25', '-focus',
        'PruneMetadataEstimate', '-base', str(capture / 'mutex-before.pprof'),
        engine, str(capture / 'mutex-after.pprof')],
}
for name, focus in [('compaction-goroutines.txt', 'compactEqClassesModeLocked'),
                    ('publication-goroutines.txt', 'publishResult'),
                    ('cache-goroutines.txt', 'dagql.*Cache')]:
    commands[name] = ['-traces', '-focus', focus, engine, str(capture / 'goroutine-008.pprof')]
for name, flags in commands.items():
    with (capture / name).open('w') as output:
        result = subprocess.run([go, 'tool', 'pprof', *flags],
            env=dict(os.environ, GOTOOLCHAIN='local'), stdout=output, stderr=subprocess.STDOUT)
    assert result.returncode == 0, name
    print(name, flush=True)
