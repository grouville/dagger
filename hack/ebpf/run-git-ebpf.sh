#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "run as root (sudo) so bpftrace can attach tracepoints"
  exit 1
fi

if ! command -v bpftrace >/dev/null 2>&1; then
  echo "bpftrace not found. Install it first (Ubuntu: apt-get install -y bpftrace)."
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "docker not found in PATH"
  exit 1
fi

engine_container="${1:-}"
if [[ -z "${engine_container}" ]]; then
  mapfile -t engines < <(docker ps --format '{{.ID}} {{.Names}}' | awk '/dagger-engine/')
  if [[ "${#engines[@]}" -eq 0 ]]; then
    echo "no running dagger-engine container found"
    echo "start a dagger command first, then rerun this script"
    exit 1
  fi
  if [[ "${#engines[@]}" -gt 1 ]]; then
    echo "multiple dagger-engine containers are running; choose one explicitly:"
    printf '  %s\n' "${engines[@]}"
    echo
    echo "usage: sudo ./hack/ebpf/run-git-ebpf.sh <container-id-or-name>"
    exit 1
  fi
  engine_container="$(awk '{print $1}' <<<"${engines[0]}")"
fi

if [[ -z "${engine_container}" ]]; then
  echo "no running dagger-engine container found"
  echo "start a dagger command first, then rerun this script"
  exit 1
fi

engine_pid="$(docker inspect -f '{{.State.Pid}}' "${engine_container}")"
engine_name="$(docker inspect -f '{{.Name}}' "${engine_container}" | sed 's#^/##')"
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
tmpl="${script_dir}/git_engine.bt"
tmp_script="$(mktemp /tmp/git-engine-ebpf.XXXXXX.bt)"

trap 'rm -f "${tmp_script}"' EXIT

seed_tracked_lines="$(
  docker top "${engine_container}" -eo pid,ppid 2>/dev/null \
    | tail -n +2 \
    | awk -v root="${engine_pid}" '
      NF >= 2 {
        pid = $1 + 0;
        ppid = $2 + 0;
        kids[ppid] = kids[ppid] " " pid;
      }
      END {
        qh = 1; qt = 1;
        q[1] = root;
        seen[root] = 1;
        while (qh <= qt) {
          cur = q[qh++];
          n = split(kids[cur], arr, /[[:space:]]+/);
          for (i = 1; i <= n; i++) {
            c = arr[i] + 0;
            if (c > 0 && !seen[c]) {
              seen[c] = 1;
              q[++qt] = c;
              if (c != root) {
                printf("  @tracked[%d] = 1;\n", c);
              }
            }
          }
        }
      }'
)"

seed_count="$(grep -c "@tracked\\[" <<<"${seed_tracked_lines}" || true)"

while IFS= read -r line; do
  line="${line//__ENGINE_PID__/${engine_pid}}"
  if [[ "${line}" == *"__SEED_TRACKED__"* ]]; then
    if [[ -n "${seed_tracked_lines}" ]]; then
      printf "%s\n" "${seed_tracked_lines}" >> "${tmp_script}"
    fi
  else
    printf "%s\n" "${line}" >> "${tmp_script}"
  fi
done < "${tmpl}"

echo "Tracing git subprocesses for container ${engine_name} (${engine_container}), host pid ${engine_pid}"
echo "Seeded ${seed_count} existing descendant pid(s) from docker top."
echo "Press Ctrl-C to stop and print histograms."
exec bpftrace "${tmp_script}"
