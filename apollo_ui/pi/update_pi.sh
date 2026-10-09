#!/usr/bin/env bash
# Signed update with controlled stop/restart of Apollo Pi user service.
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ ! -x .venv-pi/bin/python ]]; then
  echo "Run bash pi/install_pi.sh first." >&2
  exit 2
fi
WAS_RUNNING=0
if command -v systemctl >/dev/null 2>&1 &&
   systemctl --user is-active --quiet apollo-pi.service 2>/dev/null; then
  WAS_RUNNING=1
  systemctl --user stop apollo-pi.service
fi
restore() {
  if [[ "$WAS_RUNNING" == 1 ]]; then
    systemctl --user start apollo-pi.service
    echo "Apollo Pi systemd service restarted."
  fi
}
trap restore EXIT
APOLLO_PI_OFFLINE_UPDATE=1 .venv-pi/bin/python pi/update_pi.py --apply "$@"
