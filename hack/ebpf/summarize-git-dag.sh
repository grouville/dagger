#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 || $# -gt 2 ]]; then
  echo "usage: $0 <dagger-vv-log-file> [parent-op]"
  echo "example: $0 /tmp/dagger-vv.log EngineDev.test"
  exit 1
fi

log_file="$1"
parent_op="${2:-}"

awk -v parent_op="${parent_op}" '
function to_seconds(tok,   h, mi, s, n, rem) {
  h = 0; mi = 0; s = 0;
  rem = tok;

  if (match(rem, /^[0-9]+h/)) {
    n = substr(rem, 1, RLENGTH - 1);
    h = n + 0;
    rem = substr(rem, RLENGTH + 1);
  }
  if (match(rem, /^[0-9]+m/)) {
    n = substr(rem, 1, RLENGTH - 1);
    mi = n + 0;
    rem = substr(rem, RLENGTH + 1);
  }
  if (match(rem, /^[0-9]*\.?[0-9]+s$/)) {
    n = substr(rem, 1, length(rem) - 1);
    s = n + 0;
  }

  return h * 3600 + mi * 60 + s;
}

{
  # Strip ANSI escape sequences from dagger -vv output.
  esc = sprintf("%c", 27);
  gsub(esc "\\[[0-9;]*[[:alpha:]]", "", $0);

  if (match($0, /([A-Za-z][A-Za-z0-9_.]*)([[:space:]]+)(DONE|CACHED|ERROR)[[:space:]]+\[([^]]+)\]/, m)) {
    op = m[1];
    st = m[3];
    dur_tok = m[4];
    dur_s = to_seconds(dur_tok);

    if (op == "git" || op ~ /^GitRepository\./ || op ~ /^GitRef\./) {
      total_calls++;
      total_sec += dur_s;
      op_calls[op]++;
      op_sec[op] += dur_s;
      if (st == "CACHED") {
        cached_calls++;
        cached_sec += dur_s;
        op_cached[op]++;
      } else if (st == "DONE") {
        done_calls++;
        done_sec += dur_s;
      } else if (st == "ERROR") {
        err_calls++;
      }
    }

    if (parent_op != "" && op == parent_op && st == "DONE") {
      parent_done_sec = dur_s;
    }
  }
}

END {
  if (total_calls == 0) {
    print "No Git DAG operations found.";
    exit 0;
  }

  printf("Git DAG ops: calls=%d cached=%d (%.1f%%) done=%d errors=%d total_time=%.3fs\n",
    total_calls, cached_calls, (cached_calls * 100.0) / total_calls, done_calls, err_calls, total_sec);

  if (parent_op != "" && parent_done_sec > 0) {
    printf("Share of %s spent in Git DAG ops: %.1f%% (git_total=%.3fs / parent=%.3fs)\n",
      parent_op, (total_sec * 100.0) / parent_done_sec, total_sec, parent_done_sec);
  }

  print "";
  print "op,calls,cached,cache_pct,total_s,avg_s";
  for (op in op_calls) {
    c = op_calls[op];
    cc = op_cached[op] + 0;
    pct = (cc * 100.0) / c;
    t = op_sec[op];
    avg = t / c;
    printf("%s,%d,%d,%.1f,%.3f,%.3f\n", op, c, cc, pct, t, avg);
  }
}
' "${log_file}"
