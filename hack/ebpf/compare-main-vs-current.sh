#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Compare Git performance between main and current checkout using the same test command.

Usage:
  ./hack/ebpf/compare-main-vs-current.sh --engine <engine-container> [options] [-- <command...>]

Options:
  --base-ref <ref>      Baseline ref (default: main)
  --engine <name>       Dagger engine container name/id (required)
  --run <regex>         Test regex used when no custom command is provided
  --parent-op <name>    Parent op for summarize-git-vv.sh (default: EngineDev.test)
  --no-all-git          Disable --all-git eBPF mode (default uses --all-git)
  --no-ebpf             Skip eBPF capture (only parse dagger -vv logs)
  --sudo-cmd <cmd>      Override privilege wrapper for tracer start/stop (default: sudo)
                         Examples: --sudo-cmd sudo   | --sudo-cmd '' (already root)
  --cleanup             Remove temp artifact directory on exit
  --help                Show this help

If no command is provided after '--', this default is used:
  dagger -vv call engine-dev test --run '<regex>' --test-verbose
EOF
}

base_ref="main"
engine_container=""
parent_op="EngineDev.test"
use_all_git=1
use_ebpf=1
sudo_cmd="sudo"
cleanup_artifacts=0
default_run_regex='^TestGit/(TestGitTreeCacheAcrossProtocols|TestGitTreeDigestTracksContent|TestGitFunctionCacheInvalidation|TestGitRefFunctionCacheInvalidation)$'

while [[ $# -gt 0 ]]; do
  case "$1" in
    --base-ref)
      base_ref="${2:-}"
      shift 2
      ;;
    --engine)
      engine_container="${2:-}"
      shift 2
      ;;
    --run)
      default_run_regex="${2:-}"
      shift 2
      ;;
    --parent-op)
      parent_op="${2:-}"
      shift 2
      ;;
    --no-all-git)
      use_all_git=0
      shift
      ;;
    --no-ebpf)
      use_ebpf=0
      shift
      ;;
    --sudo-cmd)
      sudo_cmd="${2:-}"
      shift 2
      ;;
    --cleanup)
      cleanup_artifacts=1
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    --)
      shift
      break
      ;;
    *)
      echo "unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ -z "${engine_container}" ]]; then
  echo "--engine is required" >&2
  usage >&2
  exit 2
fi

repo_root="$(git rev-parse --show-toplevel)"
script_dir="${repo_root}/hack/ebpf"

if [[ $# -gt 0 ]]; then
  cmd=( "$@" )
else
  cmd=( dagger -vv call engine-dev test --run "${default_run_regex}" --test-verbose )
fi

if ! command -v git >/dev/null 2>&1; then
  echo "git not found in PATH" >&2
  exit 1
fi

if [[ "${use_ebpf}" -eq 1 && -n "${sudo_cmd}" ]]; then
  if ! command -v "${sudo_cmd}" >/dev/null 2>&1; then
    echo "${sudo_cmd} not found in PATH" >&2
    exit 1
  fi
fi

run_root="$(mktemp -d /tmp/dagger-git-perf-compare.XXXXXX)"
base_dir="${run_root}/base"
cur_dir="${repo_root}"

cleanup() {
  git -C "${repo_root}" worktree remove --force "${base_dir}" >/dev/null 2>&1 || true
  if [[ "${cleanup_artifacts}" -eq 1 ]]; then
    rm -rf "${run_root}" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

git -C "${repo_root}" worktree add --detach "${base_dir}" "${base_ref}" >/dev/null

run_case() {
  local label="$1"
  local dir="$2"

  local out_dir="${run_root}/${label}"
  mkdir -p "${out_dir}"

  local ebpf_log="${out_dir}/git-ebpf.log"
  local vv_log="${out_dir}/dagger-vv.log"
  local ebpf_sum="${out_dir}/ebpf-summary.txt"
  local vv_sum="${out_dir}/vv-summary.txt"
  local status_file="${out_dir}/status.txt"

  local tracer_pid=""
  local ebpf_mode=()
  if [[ "${use_all_git}" -eq 1 ]]; then
    ebpf_mode=( --all-git )
  fi

  if [[ "${use_ebpf}" -eq 1 ]]; then
    echo "== ${label}: start eBPF =="
    if [[ -n "${sudo_cmd}" ]]; then
      "${sudo_cmd}" sh -c "rm -f '${ebpf_log}'; '${script_dir}/run-git-ebpf-desktop.sh' '${engine_container}' ${ebpf_mode[*]-} | tee '${ebpf_log}'" &
    else
      sh -c "rm -f '${ebpf_log}'; '${script_dir}/run-git-ebpf-desktop.sh' '${engine_container}' ${ebpf_mode[*]-} | tee '${ebpf_log}'" &
    fi
    tracer_pid=$!

    # Give bpftrace a moment to attach before the workload starts.
    sleep 3
  fi

  echo "== ${label}: run workload =="
  printf "== %s: cmd ==\n%s\n" "${label}" "${cmd[*]}"
  local workload_rc=0
  (
    cd "${dir}"
    "${cmd[@]}"
  ) > "${vv_log}" 2>&1 || workload_rc=$?
  echo "${workload_rc}" > "${status_file}"

  if [[ "${use_ebpf}" -eq 1 ]]; then
    echo "== ${label}: stop eBPF =="
    if [[ -n "${tracer_pid}" ]]; then
      if [[ -n "${sudo_cmd}" ]]; then
        "${sudo_cmd}" kill -INT "${tracer_pid}" >/dev/null 2>&1 || true
      else
        kill -INT "${tracer_pid}" >/dev/null 2>&1 || true
      fi
      wait "${tracer_pid}" >/dev/null 2>&1 || true
    fi
    "${script_dir}/summarize-git-ebpf.sh" "${ebpf_log}" > "${ebpf_sum}" || true
  else
    printf "eBPF disabled\n" > "${ebpf_sum}"
  fi
  "${script_dir}/summarize-git-vv.sh" "${vv_log}" "${parent_op}" > "${vv_sum}" || true

  local git_span_count
  git_span_count="$(rg -c "git (fetch|ls-remote|remote|checkout|rev-parse|submodule|reset|DONE|ERROR|CACHED)" "${vv_log}" || true)"
  if [[ "${git_span_count:-0}" -eq 0 ]]; then
    echo "WARN: ${label} recorded zero low-level git spans in dagger-vv.log"
    echo "WARN: workload may have failed early or matched no tests. status=$(cat "${status_file}")"
    echo "WARN: tail of dagger-vv.log:"
    tail -n 40 "${vv_log}" || true
  fi

  echo "== ${label}: summaries =="
  cat "${ebpf_sum}"
  cat "${vv_sum}"
}

extract_metric() {
  local file="$1"
  local key="$2"
  awk -v key="${key}" '
    function emit(v){print v; found=1; exit}
    key=="ebpf.git_processes" && /^git_processes=/ {
      split($0,a,"="); emit(a[2])
    }
    key=="ebpf.dur_ms_total" {
      if (match($0,/dur_ms_total=([0-9]+)/,m)) emit(m[1])
    }
    key=="vv.dag_total" && /^== Dagger Git DAG ==/ {sec="dag"; next}
    key=="vv.cli_total" && /^== Git Subprocess Commands \(-vv\) ==/ {sec="cli"; next}
    (key=="vv.dag_total" || key=="vv.cli_total") && /^calls=/ {
      if ((key=="vv.dag_total" && sec=="dag") || (key=="vv.cli_total" && sec=="cli")) {
        if (match($0,/total=([0-9.]+)s/,m)) emit(m[1])
      }
    }
    key=="vv.subcmd.ls-remote" && $1=="ls-remote" {
      n=split($0,a,","); if (n>=3) emit(a[3])
    }
    key=="vv.subcmd.fetch" && $1=="fetch" {
      n=split($0,a,","); if (n>=3) emit(a[3])
    }
    key=="vv.subcmd.remote" && $1=="remote" {
      n=split($0,a,","); if (n>=3) emit(a[3])
    }
    key=="vv.subcmd.remote-metadata" && $1=="remote-metadata" {
      n=split($0,a,","); if (n>=3) emit(a[3])
    }
    key=="vv.subcmd.daemon" && $1=="daemon" {
      n=split($0,a,","); if (n>=3) emit(a[3])
    }
    END {
      if (!found) print "n/a"
    }
  ' "${file}"
}

emit_row() {
  local name="$1"
  local base="$2"
  local cur="$3"
  local delta
  delta="$(awk -v b="${base}" -v c="${cur}" '
    BEGIN {
      if (b=="n/a" || c=="n/a") { print "n/a"; exit }
      bb=b+0; cc=c+0
      if (bb==0) { print "n/a"; exit }
      printf("%+.1f%%", ((cc-bb)/bb)*100)
    }'
  )"
  printf "%-24s %-12s %-12s %-10s\n" "${name}" "${base}" "${cur}" "${delta}"
}

run_case "base" "${base_dir}"
run_case "current" "${cur_dir}"

base_vv="${run_root}/base/vv-summary.txt"
cur_vv="${run_root}/current/vv-summary.txt"
base_ebpf="${run_root}/base/ebpf-summary.txt"
cur_ebpf="${run_root}/current/ebpf-summary.txt"

base_dag_total="$(extract_metric "${base_vv}" "vv.dag_total")"
cur_dag_total="$(extract_metric "${cur_vv}" "vv.dag_total")"
base_cli_total="$(extract_metric "${base_vv}" "vv.cli_total")"
cur_cli_total="$(extract_metric "${cur_vv}" "vv.cli_total")"
base_lsremote="$(extract_metric "${base_vv}" "vv.subcmd.ls-remote")"
cur_lsremote="$(extract_metric "${cur_vv}" "vv.subcmd.ls-remote")"
base_fetch="$(extract_metric "${base_vv}" "vv.subcmd.fetch")"
cur_fetch="$(extract_metric "${cur_vv}" "vv.subcmd.fetch")"
base_remote="$(extract_metric "${base_vv}" "vv.subcmd.remote")"
cur_remote="$(extract_metric "${cur_vv}" "vv.subcmd.remote")"
base_remote_meta="$(extract_metric "${base_vv}" "vv.subcmd.remote-metadata")"
cur_remote_meta="$(extract_metric "${cur_vv}" "vv.subcmd.remote-metadata")"
base_daemon="$(extract_metric "${base_vv}" "vv.subcmd.daemon")"
cur_daemon="$(extract_metric "${cur_vv}" "vv.subcmd.daemon")"
base_git_proc="$(extract_metric "${base_ebpf}" "ebpf.git_processes")"
cur_git_proc="$(extract_metric "${cur_ebpf}" "ebpf.git_processes")"
base_dur_ms="$(extract_metric "${base_ebpf}" "ebpf.dur_ms_total")"
cur_dur_ms="$(extract_metric "${cur_ebpf}" "ebpf.dur_ms_total")"

echo
echo "== Comparison (base=${base_ref}, current=$(git -C "${repo_root}" rev-parse --short HEAD)) =="
printf "%-24s %-12s %-12s %-10s\n" "metric" "base" "current" "delta"
emit_row "dag_total_s" "${base_dag_total}" "${cur_dag_total}"
emit_row "cli_total_s" "${base_cli_total}" "${cur_cli_total}"
emit_row "ls_remote_s" "${base_lsremote}" "${cur_lsremote}"
emit_row "fetch_s" "${base_fetch}" "${cur_fetch}"
emit_row "remote_s" "${base_remote}" "${cur_remote}"
emit_row "remote_metadata_s" "${base_remote_meta}" "${cur_remote_meta}"
emit_row "daemon_s" "${base_daemon}" "${cur_daemon}"
emit_row "ebpf_git_processes" "${base_git_proc}" "${cur_git_proc}"
emit_row "ebpf_dur_ms_total" "${base_dur_ms}" "${cur_dur_ms}"

echo
echo "Artifacts:"
echo "  ${run_root}/base"
echo "  ${run_root}/current"
echo "  ${run_root}/base/vv-summary.txt"
echo "  ${run_root}/current/vv-summary.txt"
echo "  ${run_root}/base/ebpf-summary.txt"
echo "  ${run_root}/current/ebpf-summary.txt"
if [[ "${cleanup_artifacts}" -eq 0 ]]; then
  echo "  (retained; pass --cleanup to delete on exit)"
fi
