import os
import argparse
from pathlib import Path
import subprocess
parser=argparse.ArgumentParser()
parser.add_argument('--full-copy',action='store_true')
parser.add_argument('--engine-port',type=int,choices=[16275,16276],default=16276)
args=parser.parse_args()
base=Path('/tmp/rust-cache-sipsma-review')
def mode(value):
 if args.engine_port==16275:return
 subprocess.run(['docker','exec','-i','dagger-rust-parser-state-pool-oct14','sh','-c','cat > /tmp/filesync-snapshot-seeds-mode'],input=(value+'\n').encode(),check=True)
try:
 mode('off' if args.full_copy else 'on')
 env=dict(os.environ,RUST_CACHE_BENCH_RUNNER=f'tcp://127.0.0.1:{args.engine_port}',_EXPERIMENTAL_DAGGER_CLI_BIN=str(base/'dagger-artifact-workspace-before'))
 result=subprocess.run(['python3',str(base/'local_cli.py'),'api','with-session','--',str(base/'verify-filesync-snapshot-seeds-overlay')],env=env,cwd='/tmp/dagger-rust-config-plan-file-transfer/compiler')
 assert result.returncode==0
finally:mode('off')
