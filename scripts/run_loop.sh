#!/usr/bin/env bash
set -euo pipefail

DATA_DIR="${DATA_DIR:-/data}"
CFG="$DATA_DIR/config.env"

LOG="$DATA_DIR/iperf_log.ndjson"
ERR="$DATA_DIR/iperf_err.log"
PR="$DATA_DIR/ping_router.txt"
PE="$DATA_DIR/ping_external.txt"

[[ -f "$CFG" ]] || { echo "Missing $CFG. Run: netproof wizard"; exit 1; }
# shellcheck disable=SC1090
source "$CFG"

export TZ="${TZ:-UTC}"

run_one () {
  dir="$1"; shift
  ts="$(date -Iseconds)"
  tmp="$(mktemp /tmp/iperf_${dir}.XXXXXX.json)"

  if timeout "${TIMEOUT_SEC:-30}" iperf3 "$@" -J >"$tmp" 2>>"$ERR"; then
    if jq -e . >/dev/null 2>&1 <"$tmp"; then
      jq -c ". + {\"direction\":\"$dir\",\"timestamp\":\"$ts\"}" <"$tmp" >>"$LOG"
    else
      printf "{\"timestamp\":\"%s\",\"direction\":\"%s\",\"error\":\"jq_parse_fail\"}\n" "$ts" "$dir" >>"$LOG"
      echo "$ts $dir jq_parse_fail" >>"$ERR"
    fi
  else
    rc=$?
    printf "{\"timestamp\":\"%s\",\"direction\":\"%s\",\"error\":\"iperf_fail\",\"exit_code\":%d}\n" "$ts" "$dir" "$rc" >>"$LOG"
    echo "$ts $dir iperf_fail exit_code=$rc" >>"$ERR"
  fi
  rm -f "$tmp"
}

ping_bg () {
  target="$1"
  out="$2"
  ( ping -i 1 "$target" | while read -r line; do echo "$(date -Iseconds) $line"; done ) >>"$out" 2>&1 &
}

ping_bg "${ROUTER_IP}" "${PR}"
ping_bg "1.1.1.1" "${PE}"

echo "NetProof running. Logs in $DATA_DIR"
echo "VPS_IP=$VPS_IP ROUTER_IP=$ROUTER_IP"

while true; do
  run_one download -c "$VPS_IP" -t "${TEST_SEC:-15}" -R -b "${BANDWIDTH:-20M}" -P "${PARALLEL:-4}"
  run_one upload   -c "$VPS_IP" -t "${TEST_SEC:-15}"     -b "${BANDWIDTH:-20M}" -P "${PARALLEL:-4}"
  sleep "${INTERVAL_SEC:-60}"
done
