#!/usr/bin/env bash
set -euo pipefail

if ! command -v docker >/dev/null 2>&1; then
  echo "docker not found in PATH"
  exit 1
fi

if [[ $# -lt 1 || $# -gt 2 ]]; then
  echo "usage: $0 <engine-container-id-or-name> [--all-git]"
  echo
  echo "example:"
  echo "  $0 dagger-engine-v0.19.11"
  echo "  $0 dagger-engine-v0.19.11 --all-git"
  echo
  echo "running engine containers:"
  docker ps --format '  {{.ID}} {{.Names}}' | awk '/dagger-engine/'
  exit 1
fi

engine_container="$1"
mode="${2:-}"
if [[ -n "${mode}" && "${mode}" != "--all-git" ]]; then
  echo "invalid mode: ${mode}"
  echo "supported mode: --all-git"
  exit 1
fi

engine_pid="$(docker inspect -f '{{.State.Pid}}' "${engine_container}")"
engine_name="$(docker inspect -f '{{.Name}}' "${engine_container}" | sed 's#^/##')"

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
tmpl="${script_dir}/git_engine.bt"
if [[ "${mode}" == "--all-git" ]]; then
  tmpl="${script_dir}/git_all.bt"
fi
tmp_script="$(mktemp /tmp/git-engine-ebpf-desktop.XXXXXX.bt)"
trap 'rm -f "${tmp_script}"' EXIT

if [[ "${mode}" == "--all-git" ]]; then
  cp "${tmpl}" "${tmp_script}"
  seed_count="n/a"
else
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
fi

echo "Tracing git subprocesses for container ${engine_name} (${engine_container}), host pid ${engine_pid}"
echo "Running bpftrace inside Docker Desktop VM kernel context."
if [[ "${mode}" == "--all-git" ]]; then
  echo "Mode: --all-git (no engine process tree filtering)."
else
  echo "Seeded ${seed_count} existing descendant pid(s) from docker top."
fi
echo "Press Ctrl-C to stop and print histograms."

exec docker run --rm -i \
  --privileged \
  --pid=host \
  --cgroupns=host \
  -v /sys:/sys:ro \
  -v /lib/modules:/lib/modules:ro \
  -v "${tmp_script}:/tmp/git_engine.bt:ro" \
  quay.io/iovisor/bpftrace:latest \
  bpftrace /tmp/git_engine.bt
