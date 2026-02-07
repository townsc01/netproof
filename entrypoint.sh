#!/usr/bin/env bash
set -euo pipefail

CMD="${1:-}"
shift || true

case "$CMD" in
  wizard) exec /app/wizard.sh ;;
  run)    exec /app/scripts/run_loop.sh ;;
  report) exec python3 /app/scripts/report.py ;;
  *)
    echo "Usage:"
    echo "  netproof wizard   # create /data/config.env"
    echo "  netproof run      # start collectors"
    echo "  netproof report   # generate CSV + summary"
    exit 1
    ;;
esac
