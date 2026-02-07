#!/usr/bin/env bash
set -euo pipefail

DATA_DIR="${DATA_DIR:-/data}"
CFG="$DATA_DIR/config.env"
mkdir -p "$DATA_DIR"

echo "NetProof setup wizard"
echo ""
echo "On your VPS, run:"
echo "  sudo apt update && sudo apt install -y iperf3"
echo "  nohup iperf3 -s > /root/iperf_server.log 2>&1 &"
echo ""

read -rp "VPS public IP (required): " VPS_IP
[[ -n "${VPS_IP:-}" ]] || { echo "VPS IP required."; exit 1; }

read -rp "Router IP (default 192.168.68.1): " ROUTER_IP
ROUTER_IP="${ROUTER_IP:-192.168.68.1}"

read -rp "Bandwidth cap (e.g. 20M) [default 20M]: " BANDWIDTH
BANDWIDTH="${BANDWIDTH:-20M}"

read -rp "Test seconds [default 15]: " TEST_SEC
TEST_SEC="${TEST_SEC:-15}"

read -rp "Interval seconds between cycles [default 60]: " INTERVAL_SEC
INTERVAL_SEC="${INTERVAL_SEC:-60}"

read -rp "Parallel streams [default 4]: " PARALLEL
PARALLEL="${PARALLEL:-4}"

read -rp "Timezone [default UTC]: " TZ
TZ="${TZ:-UTC}"

cat > "$CFG" <<CFGEOF
VPS_IP=${VPS_IP}
ROUTER_IP=${ROUTER_IP}
INTERVAL_SEC=${INTERVAL_SEC}
TEST_SEC=${TEST_SEC}
BANDWIDTH=${BANDWIDTH}
PARALLEL=${PARALLEL}
TIMEOUT_SEC=30
BAD_Mbps=5
ZERO_SECS=2
TZ=${TZ}
CFGEOF

echo ""
echo "Wrote $CFG"
