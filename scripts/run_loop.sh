#!/usr/bin/env bash
set -euo pipefail

DATA_DIR="${DATA_DIR:-/data}"
CFG="$DATA_DIR/config.env"

SPEEDLOG="$DATA_DIR/speed_log.ndjson"
IPERFLOG="$DATA_DIR/iperf_log.ndjson"
ERR="$DATA_DIR/run_err.log"
PR="$DATA_DIR/ping_router.txt"
PE="$DATA_DIR/ping_external.txt"

[[ -f "$CFG" ]] || { echo "Missing $CFG. Run: netproof wizard"; exit 1; }
# shellcheck disable=SC1090
source "$CFG"

export TZ="${TZ:-UTC}"
MODE="${MODE:-speedtest}"

PING_PIDS=()

cleanup() {
  echo "Stopping..."
  for pid in "${PING_PIDS[@]:-}"; do kill "$pid" 2>/dev/null || true; done
  pkill -f "iperf3 -c" 2>/dev/null || true
  wait 2>/dev/null || true
  exit 0
}
trap cleanup SIGINT SIGTERM

ping_bg () {
  target="$1"
  out="$2"
  ( ping -i 1 "$target" | while read -r line; do echo "$(date -Iseconds) $line"; done ) >>"$out" 2>&1 &
  echo $!
}

run_speedtest () {
  ts="$(date -Iseconds)"
  tmp="$(mktemp /tmp/speedtest.XXXXXX.json)"

  # Speedtest CLI: JSON output
  # Accept license + GDPR flags are required for non-interactive use
  if timeout "${TIMEOUT_SEC:-60}" speedtest --accept-license --accept-gdpr -f json >"$tmp" 2>>"$ERR"; then
    if jq -e . >/dev/null 2>&1 <"$tmp"; then
      # Slim it down but keep raw too
      jq -c '{
        timestamp: $ts,
        mode: "speedtest",
        isp: .isp,
        server: (.server.name // "") ,
        server_location: ((.server.location // "") + (if .server.country then ", " + .server.country else "" end)),
        ping_ms: (.ping.latency // null),
        jitter_ms: (.ping.jitter // null),
        download_mbps: (if .download.bandwidth then (.download.bandwidth * 8 / 1000000) else null end),
        upload_mbps: (if .upload.bandwidth then (.upload.bandwidth * 8 / 1000000) else null end),
        packet_loss: (.packetLoss // null),
        result_url: (.result.url // null),
        error: null
      }' --arg ts "$ts" <"$tmp" >>"$SPEEDLOG"
    else
      printf '{"timestamp":"%s","mode":"speedtest","error":"jq_parse_fail"}\n' "$ts" >>"$SPEEDLOG"
    fi
  else
    rc=$?
    printf '{"timestamp":"%s","mode":"speedtest","error":"speedtest_fail","exit_code":%d}\n' "$ts" "$rc" >>"$SPEEDLOG"
  fi

  rm -f "$tmp"
}

run_iperf_one () {
  dir="$1"; shift
  ts="$(date -Iseconds)"
  tmp="$(mktemp /tmp/iperf_${dir}.XXXXXX.json)"

  if timeout "${TIMEOUT_SEC:-60}" iperf3 "$@" -J >"$tmp" 2>>"$ERR"; then
    if jq -e . >/dev/null 2>&1 <"$tmp"; then
      jq -c ". + {\"direction\":\"$dir\",\"timestamp\":\"$ts\"}" <"$tmp" >>"$IPERFLOG"
    else
      printf '{"timestamp":"%s","direction":"%s","error":"jq_parse_fail"}\n' "$ts" "$dir" >>"$IPERFLOG"
    fi
  else
    rc=$?
    printf '{"timestamp":"%s","direction":"%s","error":"iperf_fail","exit_code":%d}\n' "$ts" "$dir" "$rc" >>"$IPERFLOG"
  fi

  rm -f "$tmp"
}

echo "Starting pings..."
PING_PIDS+=("$(ping_bg "${ROUTER_IP:-192.168.68.1}" "${PR}")")
PING_PIDS+=("$(ping_bg "1.1.1.1" "${PE}")")

echo "NetProof running. Logs in $DATA_DIR"
echo "MODE=$MODE ROUTER_IP=${ROUTER_IP:-}"

while true; do
  if [[ "$MODE" == "speedtest" ]]; then
    run_speedtest
  else
    [[ -n "${VPS_IP:-}" ]] || { echo "VPS_IP missing for iperf mode." >&2; exit 1; }
    run_iperf_one download -c "$VPS_IP" -t "${TEST_SEC:-15}" -R -b "${BANDWIDTH:-20M}" -P "${PARALLEL:-4}"
    run_iperf_one upload   -c "$VPS_IP" -t "${TEST_SEC:-15}"     -b "${BANDWIDTH:-20M}" -P "${PARALLEL:-4}"
  fi
  sleep "${INTERVAL_SEC:-300}"
done
