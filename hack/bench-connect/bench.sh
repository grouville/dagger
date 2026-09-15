#!/usr/bin/env bash
# Standalone connect benchmark: how long `dagger query '{version}'` takes,
# which is connect plus one trivial round trip, over each transport the CLI
# can use to reach a local docker engine. Runs n samples per transport,
# interleaved, and prints medians.
#
# usage: hack/bench-connect/bench.sh [-n 10] [-i IMAGE] [-c CONTAINER]
#   IMAGE      engine image to run (default: the CLI's own engine image)
#   CONTAINER  container name (default: bench-connect)
#
# Transports measured on the same engine container:
#   endpoint   token-protected loopback port (image driver default)
#   exec       docker exec tunnel (the fallback: token file hidden)
#   container  container:// scheme (exec tunnel, no discovery)
#   tcp        a plain tcp:// listener if the engine was started with ?port=
set -eu
n=10; image=""; name="bench-connect"; port=""
while getopts "n:i:c:p:" o; do case $o in n) n=$OPTARG;; i) image=$OPTARG;; c) name=$OPTARG;; p) port=$OPTARG;; esac; done
dagger=${DAGGER:-dagger}
image=${image:-$($dagger version 2>/dev/null | awk '/runner-host/ {sub("image://",""); print $2}')}
export DO_NOT_TRACK=1
dir=${XDG_STATE_HOME:-$HOME/.local/state}/dagger/engines/$name
url="image://$image?container=$name&volume=$name"
[ -n "$port" ] && url="$url&port=$port"

median() { sort -n | awk '{a[NR]=$1} END{print (NR%2? a[(NR+1)/2] : (a[NR/2]+a[NR/2+1])/2)}'; }
sample() { local s e; s=$(date +%s%N); DAGGER_ENGINE="$1" $dagger query >/dev/null 2>&1 <<< '{version}'; e=$(date +%s%N); echo $(( (e-s)/1000000 )); }

echo "engine image: $image  container: $name  samples: $n"
DAGGER_ENGINE="$url" $dagger query >/dev/null 2>&1 <<< '{version}' || { echo "engine did not start"; exit 1; }
declare -A results
transports=(endpoint exec container)
[ -n "$port" ] && transports+=(tcp)
for i in $(seq 1 "$n"); do
  for t in "${transports[@]}"; do
    case $t in
      endpoint)  ms=$(sample "$url") ;;
      exec)      mv "$dir/token" "$dir/token.hidden"; ms=$(sample "$url"); mv "$dir/token.hidden" "$dir/token" ;;
      container) ms=$(sample "container://$name") ;;
      tcp)       ms=$(sample "tcp://127.0.0.1:$port") ;;
    esac
    results[$t]="${results[$t]:-} $ms"
  done
done
printf "%-10s %8s %8s\n" transport median min
for t in "${transports[@]}"; do
  printf "%-10s %8s %8s\n" "$t" "$(echo ${results[$t]} | tr ' ' '\n' | median)" "$(echo ${results[$t]} | tr ' ' '\n' | sort -n | head -1)"
done
