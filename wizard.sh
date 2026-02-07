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

# allow numeric shortcuts
if [[ "$MODE" == "1" ]]; then MODE="speedtest"; fi
if [[ "$MODE" == "2" ]]; then MODE="iperf"; fi

if [[ "$MODE" != "speedtest" && "$MODE" != "iperf" ]]; then
  echo "Mode must be speedtest or iperf (you can also enter 1 or 2)." >&2
  exit 1
fi

# -------- base settings (both modes) --------
echo ""
read -rp "Router IP (default 192.168.68.1): " ROUTER_IP
ROUTER_IP="${ROUTER_IP:-192.168.68.1}"

read -rp "Interval seconds between cycles [default 300]: " INTERVAL_SEC
INTERVAL_SEC="${INTERVAL_SEC:-300}"

read -rp "Timeout seconds per test [default 60]: " TIMEOUT_SEC
TIMEOUT_SEC="${TIMEOUT_SEC:-60}"

read -rp "Timezone [default UTC]: " TZ
TZ="${TZ:-UTC}"

# -------- slowdown detection (reports) --------
echo ""
echo "Slowdown detection (used in reports)"
echo "If you enter advertised speeds, a slowdown is flagged when measured speed is below a % of advertised."
echo "If advertised is blank/incomplete, NetProof falls back to absolute minimum thresholds."
echo ""

read -rp "Advertised download Mbps (optional, e.g. 50) []: " ADVERTISED_DOWN
read -rp "Advertised upload Mbps (optional, e.g. 20) []: " ADVERTISED_UP

read -rp "Flag slowdown below what % of advertised? [default 25]: " SLOWDOWN_PCT
SLOWDOWN_PCT="${SLOWDOWN_PCT:-25}"

ABS_MIN_DOWN=""
ABS_MIN_UP=""

# Only ask for absolute mins if advertised isn't fully provided
if [[ -z "${ADVERTISED_DOWN}" || -z "${ADVERTISED_UP}" ]]; then
  echo ""
  echo "Advertised speeds not fully provided — using fallback absolute minimum thresholds."
  read -rp "Absolute min download Mbps [default 5]: " ABS_MIN_DOWN
  ABS_MIN_DOWN="${ABS_MIN_DOWN:-5}"

  read -rp "Absolute min upload Mbps [default 2]: " ABS_MIN_UP
  ABS_MIN_UP="${ABS_MIN_UP:-2}"
fi

# -------- iperf-only settings --------
VPS_IP=""
IPERF_TEST_SEC=""
IPERF_BW_Mbps=""
IPERF_PARALLEL=""

if [[ "$MODE" == "iperf" ]]; then
  echo ""
  echo "On your VPS, run:"
  echo "  sudo apt update && sudo apt install -y iperf3"
  echo "  nohup iperf3 -s > /root/iperf_server.log 2>&1 &"
  echo ""
  read -rp "VPS public IP (required for iperf): " VPS_IP
  [[ -n "${VPS_IP:-}" ]] || { echo "VPS IP required for iperf mode." >&2; exit 1; }

  echo ""
  read -rp "iperf test seconds [default 15]: " IPERF_TEST_SEC
  IPERF_TEST_SEC="${IPERF_TEST_SEC:-15}"

  echo "iperf bandwidth cap is optional."
  echo "Enter Mbps (e.g. 50, 250, 900). Leave blank for uncapped."
  read -rp "iperf bandwidth cap Mbps (optional) []: " IPERF_BW_Mbps

  read -rp "iperf parallel streams [default 4]: " IPERF_PARALLEL
  IPERF_PARALLEL="${IPERF_PARALLEL:-4}"
fi

# -------- write config --------
cat > "$CFG" <<CFGEOF
MODE=${MODE}
VPS_IP=${VPS_IP}
ROUTER_IP=${ROUTER_IP}
INTERVAL_SEC=${INTERVAL_SEC}
TIMEOUT_SEC=${TIMEOUT_SEC}
TZ=${TZ}

# Report thresholds
ADVERTISED_DOWN_Mbps=${ADVERTISED_DOWN}
ADVERTISED_UP_Mbps=${ADVERTISED_UP}
SLOWDOWN_PCT=${SLOWDOWN_PCT}
ABS_MIN_DOWN_Mbps=${ABS_MIN_DOWN}
ABS_MIN_UP_Mbps=${ABS_MIN_UP}

# iperf-only (used when MODE=iperf)
IPERF_TEST_SEC=${IPERF_TEST_SEC}
IPERF_BW_Mbps=${IPERF_BW_Mbps}
IPERF_PARALLEL=${IPERF_PARALLEL}
CFGEOF

echo ""
echo "Wrote $CFG"
