#!/usr/bin/env bash
# Install Apollo's minimal Raspberry Pi headless runtime from the checked-out repo.
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ "$(uname -s)" != Linux || "$(uname -m)" != aarch64 ]]; then
  echo "Apollo Pi installer requires 64-bit ARM Linux (aarch64)." >&2
  exit 2
fi
python3 -c 'import sys; assert sys.version_info >= (3, 11), "Python >=3.11 required"'
python3 -m venv .venv-pi
.venv-pi/bin/python -m pip install 'cryptography>=42,<50'
.venv-pi/bin/python apollo_pi.py --self-test
echo
echo "Core installed. Install Ollama for ARM64 separately and pull a small model:"
echo "  ollama pull qwen2.5:3b"
echo "Run the private local API:"
echo "  .venv-pi/bin/python apollo_pi.py --port 8766"
echo
echo "To enable a user-level systemd service:"
echo "  bash pi/install_pi.sh --service"
if [[ $# -gt 0 && "$1" == "--service" ]]; then
  if [[ "$PWD" =~ [[:space:]%] ]]; then
    echo "Service path cannot contain spaces or %; move Apollo to a simpler directory." >&2
    exit 2
  fi
  mkdir -p "$HOME/.config/systemd/user"
  cat > "$HOME/.config/systemd/user/apollo-pi.service" <<UNIT
[Unit]
Description=Apollo Local Raspberry Pi Headless Assistant
After=network.target

[Service]
Type=simple
WorkingDirectory=$PWD
ExecStart=$PWD/.venv-pi/bin/python $PWD/apollo_pi.py --port 8766
Restart=on-failure
RestartSec=8
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=default.target
UNIT
  systemctl --user daemon-reload
  systemctl --user enable --now apollo-pi.service
  echo "Service enabled. Logs: journalctl --user -u apollo-pi.service -f"
fi
