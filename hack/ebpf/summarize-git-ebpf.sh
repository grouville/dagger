#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: $0 <ebpf-output-log>"
  echo "example: $0 /tmp/git-ebpf.log"
  exit 1
fi

log_file="$1"

awk '
/git_exit / {
  dur = 0; conn = 0; sendb = 0; recvb = 0;
  if (match($0, /dur_ms=([0-9]+)/, d)) {
    dur = d[1] + 0;
  }
  if (match($0, /conn_ms=([0-9]+)/, c)) {
    conn = c[1] + 0;
  }
  if (match($0, /send_bytes=([0-9]+)/, s)) {
    sendb = s[1] + 0;
  }
  if (match($0, /recv_bytes=([0-9]+)/, r)) {
    recvb = r[1] + 0;
  }

  n++;
  dsum += dur;
  csum += conn;
  ssum += sendb;
  rsum += recvb;
  durs[n] = dur;
}

END {
  if (n == 0) {
    print "no git_exit events found";
    exit 0;
  }

  # median of dur_ms
  asort(durs);
  if (n % 2 == 1) {
    med = durs[(n + 1) / 2];
  } else {
    med = (durs[n / 2] + durs[n / 2 + 1]) / 2.0;
  }

  printf("git_processes=%d\n", n);
  printf("dur_ms_total=%d dur_ms_avg=%.1f dur_ms_median=%.1f\n", dsum, dsum / n, med);
  printf("conn_ms_total=%d conn_ms_avg=%.1f\n", csum, csum / n);
  printf("conn_share_of_dur=%.1f%%\n", (dsum > 0 ? (100.0 * csum / dsum) : 0));
  printf("send_bytes_total=%d recv_bytes_total=%d\n", ssum, rsum);
}
' "${log_file}"
