#!/usr/bin/env bash
set -euo pipefail

DATA_DIR="${DATA_DIR:-/data}"
CFG="$DATA_DIR/config.env"

IPERFLOG="$DATA_DIR/iperf_log.ndjson"
IPERFERR="$DATA_DIR/iperf_err.log"
SPEEDLOG="$DATA_DIR/speed_log.ndjson"
ERR="$DATA_DIR/collector_err.log"

PR="$DATA_DIR/ping_router.txt"
PE="$DATA_DIR/ping_external.txt"

mkdir -p "$DATA_DIR"
[[ -f "$CFG" ]] || { echo "Missing $CFG. Run: netproof wizard" >&2; exit 1; }

# shellcheck disable=SC1090
source "$CFG"

export TZ="${TZ:-UTC}"

# ---- knobs (sane defaults) ----
SPEEDTEST_RETRIES="${SPEEDTEST_RETRIES:-3}"
SPEEDTEST_BACKOFF_BASE_S="${SPEEDTEST_BACKOFF_BASE_S:-5}"

PING_PIDS=()

cleanup() {
  echo "Stopping..."
  for pid in "${PING_PIDS[@]:-}"; do
    kill "$pid" >/dev/null 2>&1 || true
  done
}
trap cleanup INT TERM EXIT

ping_bg () {
  target="$1"
  out="$2"
  ( ping -i 1 "$target" | while read -r line; do echo "$(date -Iseconds) $line"; done ) >>"$out" 2>&1 &
  echo $!
}

# ---------- iperf helpers ----------
run_iperf_one () {
  local dir="$1"; shift
  local ts tmp attempts rc busy

  ts="$(date -Iseconds)"
  tmp="$(mktemp "/tmp/iperf_${dir}.XXXXXX.json")"

  attempts=0
  while true; do
    attempts=$((attempts+1))

    if timeout "${TIMEOUT_SEC:-60}" iperf3 "$@" -J >"$tmp" 2>>"$ERR"; then
      if jq -e . >/dev/null 2>&1 <"$tmp"; then
        busy="$(jq -r '.error // ""' <"$tmp")"
        if echo "$busy" | grep -qi "server is busy" && [[ $attempts -lt 3 ]]; then
          sleep $((10 * attempts))
          continue
        fi
        jq -c ". + {\"direction\":\"$dir\",\"timestamp\":\"$ts\",\"attempts\":$attempts}" <"$tmp" >>"$IPERFLOG"
      else
        printf '{"timestamp":"%s","direction":"%s","error":"jq_parse_fail","attempts":%d}\n' \
          "$ts" "$dir" "$attempts" >>"$IPERFLOG"
      fi
    else
      rc=$?
      printf '{"timestamp":"%s","direction":"%s","error":"iperf_fail","exit_code":%d,"attempts":%d}\n' \
        "$ts" "$dir" "$rc" "$attempts" >>"$IPERFLOG"
    fi

    break
  done

  rm -f "$tmp"
}

# ---------- speedtest helper ----------
dns_warmup () {
  # Do NOT fail the run if DNS warmup fails; it's just a best-effort nudge.
  getent hosts config.speedtest.net >/dev/null 2>&1 || true
  getent hosts www.google.com >/dev/null 2>&1 || true
}

run_speedtest () {
  local ts tmp errtmp rc attempt sleep_s errtail

  ts="$(date -Iseconds)"
  tmp="$(mktemp /tmp/speedtest.XXXXXX.json)"
  errtmp="$(mktemp /tmp/speedtest.XXXXXX.err)"

  # Warm up DNS (helps with "couldn't resolve host" right after container start)
  dns_warmup

  attempt=1
  while [[ $attempt -le $SPEEDTEST_RETRIES ]]; do
    : >"$errtmp"

    if timeout "${TIMEOUT_SEC:-60}" speedtest --accept-license --accept-gdpr -f json >"$tmp" 2>>"$errtmp"; then
      if jq -e . >/dev/null 2>&1 <"$tmp"; then
        jq -c ". + {\"timestamp\":\"$ts\",\"source\":\"speedtest\",\"attempts\":$attempt}" <"$tmp" >>"$SPEEDLOG"
        rm -f "$tmp" "$errtmp"
        return 0
      fi

      errtail="$(tail -n 8 "$errtmp" 2>/dev/null | tr '\n' ' ' | sed 's/[[:space:]]\+/ /g' | cut -c1-400)"
      printf '{"timestamp":"%s","source":"speedtest","error":"jq_parse_fail","attempts":%d,"stderr_tail":"%s"}\n' \
        "$ts" "$attempt" "${errtail//\"/\\\"}" >>"$SPEEDLOG"
      rm -f "$tmp" "$errtmp"
      return 0
    fi

    rc=$?
    errtail="$(tail -n 8 "$errtmp" 2>/dev/null | tr '\n' ' ' | sed 's/[[:space:]]\+/ /g' | cut -c1-400)"
    printf '{"timestamp":"%s","source":"speedtest","error":"speedtest_fail","exit_code":%d,"attempts":%d,"stderr_tail":"%s"}\n' \
      "$ts" "$rc" "$attempt" "${errtail//\"/\\\"}" >>"$SPEEDLOG"

    # Backoff and retry (handles transient DNS/config fetch failures)
    sleep_s=$((SPEEDTEST_BACKOFF_BASE_S * attempt))
    sleep "$sleep_s"
    dns_warmup
    attempt=$((attempt+1))
  done

  rm -f "$tmp" "$errtmp"
  return 0
}

# ---------- main ----------
echo "Starting pings..."
PING_PIDS+=("$(ping_bg "${ROUTER_IP:-192.168.68.1}" "${PR}")")
PING_PIDS+=("$(ping_bg "1.1.1.1" "${PE}")")

echo "NetProof running. Logs in $DATA_DIR"
echo "MODE=${MODE:-speedtest} ROUTER_IP=${ROUTER_IP:-}"

# In speedtest mode, don't leave confusing iperf artifacts around
if [[ "${MODE:-speedtest}" == "speedtest" ]]; then
  rm -f "$IPERFLOG" "$IPERFERR" >/dev/null 2>&1 || true
fi

while true; do
  if [[ "${MODE:-speedtest}" == "speedtest" ]]; then
    run_speedtest
  else
    [[ -n "${VPS_IP:-}" ]] || { echo "VPS_IP missing for iperf mode." >&2; exit 1; }

    tsec="${IPERF_TEST_SEC:-15}"
    par="${IPERF_PARALLEL:-4}"

    bw_arg=()
    if [[ -n "${IPERF_BW_Mbps:-}" ]]; then
      bw_arg=(-b "${IPERF_BW_Mbps}M")
    fi

    run_iperf_one download -c "$VPS_IP" -t "$tsec" -R "${bw_arg[@]}" -P "$par"
    run_iperf_one upload   -c "$VPS_IP" -t "$tsec"     "${bw_arg[@]}" -P "$par"
  fi

  sleep "${INTERVAL_SEC:-300}"
done
