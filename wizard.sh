#!/usr/bin/env bash
set -euo pipefail

DATA_DIR="${DATA_DIR:-/data}"
CFG="$DATA_DIR/config.env"
mkdir -p "$DATA_DIR"

echo "NetProof setup wizard"
echo ""
echo "Choose test mode:"
echo "  1) speedtest  (recommended: no VPS needed)"
echo "  2) iperf      (advanced: requires your own VPS running iperf3 -s)"
echo ""

read -rp "Mode [speedtest]: " MODE
MODE="${MODE:-speedtest}"

if [[ "$MODE" != "speedtest" && "$MODE" != "iperf" ]]; then
  echo "Mode must be 'speedtest' or 'iperf'." >&2
  exit 1
fi

VPS_IP=""
if [[ "$MODE" == "iperf" ]]; then
  echo ""
  echo "On your VPS, run:"
  echo "  sudo apt update && sudo apt install -y iperf3"
  echo "  nohup iperf3 -s > /root/iperf_server.log 2>&1 &"
  echo ""
  read -rp "VPS public IP (required for iperf): " VPS_IP
  [[ -n "${VPS_IP:-}" ]] || { echo "VPS IP required for iperf mode."; exit 1; }
fi

read -rp "Router IP (default 192.168.68.1): " ROUTER_IP
ROUTER_IP="${ROUTER_IP:-192.168.68.1}"

read -rp "Interval seconds between cycles [default 300]: " INTERVAL_SEC
INTERVAL_SEC="${INTERVAL_SEC:-300}"

read -rp "Timezone [default UTC]: " TZ
TZ="${TZ:-UTC}"

# iperf-only knobs (harmless defaults for speedtest mode)
read -rp "iperf test seconds [default 15]: " TEST_SEC
TEST_SEC="${TEST_SEC:-15}"

read -rp "iperf bandwidth cap (e.g. 20M) [default 20M]: " BANDWIDTH
BANDWIDTH="${BANDWIDTH:-20M}"

read -rp "iperf parallel streams [default 4]: " PARALLEL
PARALLEL="${PARALLEL:-4}"

cat > "$CFG" <<CFGEOF
MODE=${MODE}
VPS_IP=${VPS_IP}
ROUTER_IP=${ROUTER_IP}
INTERVAL_SEC=${INTERVAL_SEC}
TEST_SEC=${TEST_SEC}
BANDWIDTH=${BANDWIDTH}
PARALLEL=${PARALLEL}
TIMEOUT_SEC=60
BAD_Mbps=5
ZERO_SECS=2
TZ=${TZ}
CFGEOF

echo ""
echo "Wrote $CFG"
