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

function extract_git_cmd(line,   s) {
  s = line;
  # Extract the first git command span from a traced line.
  # This avoids grabbing the final "git " in paths like ".../.git ...".
  if (!match(s, /(^|[[:space:]])git[[:space:]][^[:cntrl:]]*$/)) {
    return "";
  }
  s = substr(s, RSTART, RLENGTH);
  sub(/^[[:space:]]+/, "", s);
  return s;
}

function git_subcmd(cmd,   n, a, i, t) {
  # Split out expensive pseudo-commands emitted by engine instrumentation.
  if (cmd ~ /^git remote metadata([[:space:]]|$)/) return "remote-metadata";
  if (cmd ~ /^git ls-remote([[:space:]]|$)/) return "ls-remote";
  if (cmd ~ /^git fetch([[:space:]]|$)/) return "fetch";
  if (cmd ~ /^git daemon([[:space:]]|$)/) return "daemon";

  n = split(cmd, a, /[[:space:]]+/);
  # cmd starts with git
  for (i = 2; i <= n; i++) {
    t = a[i];
    if (t == "-c") {
      i++;
      continue;
    }
    if (substr(t, 1, 1) == "-") {
      continue;
    }
    return t;
  }
  return "(unknown)";
}

{
  # Strip ANSI escape sequences from dagger -vv output.
  esc = sprintf("%c", 27);
  gsub(esc "\\[[0-9;]*[[:alpha:]]", "", $0);

  if (!match($0, /(DONE|CACHED|ERROR)[[:space:]]+\[([^]]+)\]/, m)) {
    next;
  }

  st = m[1];
  dur_tok = m[2];
  pre = substr($0, 1, RSTART - 1);
  gsub(/[[:space:]]+$/, "", pre);
  dur_s = to_seconds(dur_tok);

  # parent op for share (% of call)
  if (parent_op != "" && match(pre, /([A-Za-z][A-Za-z0-9_.]*)$/, pm)) {
    if (pm[1] == parent_op && st == "DONE") {
      parent_done_sec = dur_s;
    }
  }

  # DAG Git operations (cache observability at DAG layer)
  if (match(pre, /([A-Za-z][A-Za-z0-9_.]*)$/, om)) {
    op = om[1];
    if (op == "git" || op ~ /^GitRepository\./ || op ~ /^GitRef\./) {
      dag_calls++;
      dag_sec += dur_s;
      dag_op_calls[op]++;
      dag_op_sec[op] += dur_s;
      if (st == "CACHED") {
        dag_cached_calls++;
        dag_cached_sec += dur_s;
        dag_op_cached[op]++;
      } else if (st == "DONE") {
        dag_done_calls++;
      } else if (st == "ERROR") {
        dag_err_calls++;
      }
    }
  }

  # Low-level git subprocess commands from -vv logs
  if (index(pre, "git ") == 0) {
    next;
  }

  cmd = extract_git_cmd(pre);
  gsub(/[[:space:]]+$/, "", cmd);
  if (cmd == "git") {
    next;
  }

  subcmd = git_subcmd(cmd);

  cli_calls++;
  cli_sec += dur_s;
  cli_sub_calls[subcmd]++;
  cli_sub_sec[subcmd] += dur_s;
  cli_sub_st[subcmd SUBSEP st]++;
  cli_cmd_calls[cmd]++;
  cli_cmd_sec[cmd] += dur_s;

  if (st == "CACHED") {
    cli_cached_calls++;
  } else if (st == "DONE") {
    cli_done_calls++;
  } else if (st == "ERROR") {
    cli_err_calls++;
  }
}

END {
  print "== Dagger Git DAG ==";
  if (dag_calls == 0) {
    print "no Git DAG ops found";
  } else {
    printf("calls=%d cached=%d (%.1f%%) done=%d errors=%d total=%.3fs\n",
      dag_calls, dag_cached_calls, (dag_cached_calls * 100.0) / dag_calls, dag_done_calls, dag_err_calls, dag_sec);
    if (parent_op != "" && parent_done_sec > 0) {
      printf("share_of_%s=%.1f%% (git_dag=%.3fs / parent=%.3fs)\n",
        parent_op, (dag_sec * 100.0) / parent_done_sec, dag_sec, parent_done_sec);
    }
    print "";
    print "op,calls,cached,cache_pct,total_s,avg_s";
    ndagops = asorti(dag_op_calls, dag_op_names);
    for (i = 1; i <= ndagops; i++) {
      op = dag_op_names[i];
      c = dag_op_calls[op];
      cc = dag_op_cached[op] + 0;
      t = dag_op_sec[op];
      printf("%s,%d,%d,%.1f,%.3f,%.3f\n", op, c, cc, (cc * 100.0) / c, t, t / c);
    }
  }

  print "";
  print "== Git Subprocess Commands (-vv) ==";
  if (cli_calls == 0) {
    print "no low-level git command spans found";
    exit 0;
  }

  printf("calls=%d cached=%d (%.1f%%) done=%d errors=%d total=%.3fs avg=%.3fs\n",
    cli_calls, cli_cached_calls, (cli_cached_calls * 100.0) / cli_calls, cli_done_calls, cli_err_calls, cli_sec, cli_sec / cli_calls);

  print "";
  print "subcmd,calls,total_s,avg_s,cached,done,error";
  nsubs = asorti(cli_sub_calls, sub_names);
  for (i = 1; i <= nsubs; i++) {
    s = sub_names[i];
    c = cli_sub_calls[s];
    t = cli_sub_sec[s];
    cc = cli_sub_st[s SUBSEP "CACHED"] + 0;
    dc = cli_sub_st[s SUBSEP "DONE"] + 0;
    ec = cli_sub_st[s SUBSEP "ERROR"] + 0;
    printf("%s,%d,%.3f,%.3f,%d,%d,%d\n", s, c, t, t / c, cc, dc, ec);
  }

  print "";
  print "top_cmd,total_s,calls,avg_s";
  ncmds = asorti(cli_cmd_calls, cmd_names);
  for (i = 1; i <= ncmds; i++) {
    cmd = cmd_names[i];
    c = cli_cmd_calls[cmd];
    t = cli_cmd_sec[cmd];
    printf("%s,%.3f,%d,%.3f\n", cmd, t, c, t / c);
  }
}
' "${log_file}"
