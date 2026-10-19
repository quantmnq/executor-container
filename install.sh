#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Follow Executor contributors
set -euo pipefail
umask 077
repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
if [[ $EUID -eq 0 ]]; then
    echo 'Run ./install.sh as your Ubuntu login user, without sudo.' >&2
    exit 1
fi
if [[ $repo_dir =~ [[:space:]%] ]]; then
    echo 'Use a checkout path without whitespace or percent signs.' >&2
    exit 1
fi
source /etc/os-release
if [[ $ID != ubuntu || $VERSION_ID != 24.04 ]]; then
    echo 'This installer targets Ubuntu 24.04 LTS (OCI Ampere ARM64 or x86_64).' >&2
    exit 1
fi
if systemctl --user is-active --quiet follow-executor.service; then
    echo 'Executor is running. Wait until flat, then ./follow stop before installing/upgrading.' >&2
    exit 1
fi
if systemctl --user is-active --quiet follow-gateway.service; then
    echo 'Stop trading while flat, then ./follow gateway stop before upgrading.' >&2
    exit 1
fi
sudo apt-get update
sudo apt-get install -y python3-venv python3-pip curl unzip ca-certificates x11-utils tzdata
python3 -m venv "$repo_dir/.venv"
"$repo_dir/.venv/bin/python" -m pip install --upgrade pip
"$repo_dir/.venv/bin/python" -m pip install "$repo_dir"
"$repo_dir/scripts/install-ibapi.sh"
"$repo_dir/scripts/install-ibc.sh"
unit_dir="$HOME/.config/systemd/user"
mkdir -p "$unit_dir"
# Paths are literal, quoted systemd arguments; do not put tokens in the unit.
cat > "$unit_dir/follow-executor.service" <<EOF
[Unit]
Description=Follow Executor — own-account MNQ/NQ follower
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$repo_dir
ExecStart="$repo_dir/.venv/bin/follow-executor" run --config "$HOME/.config/follow-executor/executor.json"
Environment=PYTHONUNBUFFERED=1
Restart=on-failure
RestartSec=10
RestartPreventExitStatus=2
TimeoutStopSec=45
UMask=0077
NoNewPrivileges=true

[Install]
WantedBy=default.target
EOF
systemctl --user daemon-reload
"$repo_dir/.venv/bin/follow-executor" gateway --config "$HOME/.config/follow-executor/executor.json" refresh
sudo loginctl enable-linger "$(id -un)"
echo 'Installed. Next: ./scripts/gateway-desktop.sh, then ./follow gateway configure. See docs/SETUP.md.'
echo 'Trading has not been started. Keep this repository at its current path.'
