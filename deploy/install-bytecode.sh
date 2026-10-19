#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Follow Executor contributors
# Installed as install.sh in the customer kit. No application source is required.
set -euo pipefail
umask 077
release_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
if [[ $EUID -eq 0 ]]; then
    echo 'Run ./install.sh as your Ubuntu login user, without sudo.' >&2
    exit 1
fi
if [[ $release_dir =~ [[:space:]%] || $HOME =~ [[:space:]%] ]]; then
    echo 'Use installation and home paths without whitespace or percent signs.' >&2
    exit 1
fi
source /etc/os-release
if [[ $ID != ubuntu || $VERSION_ID != 24.04 || $(uname -m) != aarch64 ]]; then
    echo 'This bytecode release requires Ubuntu 24.04 LTS on ARM64 (aarch64).' >&2
    exit 1
fi
cd -- "$release_dir"
sha256sum --check --strict SHA256SUMS
python3.12 -I - <<'PY'
import importlib.util
import json
import sys
release = json.load(open('RELEASE.json'))
if (sys.implementation.name != 'cpython' or sys.version_info[:2] != (3, 12)
        or importlib.util.MAGIC_NUMBER.hex() != release['bytecode_magic']):
    raise SystemExit('This release requires compatible CPython 3.12 bytecode.')
PY
if [[ ${1:-} == --verify-only && $# == 1 ]]; then
    echo 'Release checksums, OS, architecture and Python bytecode version verified.'
    exit 0
fi
if [[ $# != 0 ]]; then
    echo 'Usage: ./install.sh [--verify-only]' >&2
    exit 1
fi
service_state=$(systemctl --user show follow-executor.service -p ActiveState --value)
case "$service_state" in
    active|activating|reloading|deactivating)
        echo 'Executor is running. Wait until flat, then ./follow stop before installing.' >&2
        exit 1 ;;
esac
gateway_state=$(systemctl --user show follow-gateway.service -p ActiveState --value)
case "$gateway_state" in
    active|activating|reloading|deactivating)
        echo 'Stop trading while flat, then ./follow gateway stop before upgrading.' >&2
        exit 1 ;;
esac
sudo apt-get update
sudo apt-get install -y python3.12-venv python3-pip curl unzip ca-certificates x11-utils tzdata
python3.12 -m venv "$release_dir/.venv"
python_bin="$release_dir/.venv/bin/python"
"$python_bin" -m pip install --upgrade pip
wheels=("$release_dir"/wheels/follow_executor-*-cp312-none-any.whl)
if [[ ${#wheels[@]} != 1 || ! -f ${wheels[0]} ]]; then
    echo 'Expected exactly one CPython 3.12 application wheel.' >&2
    exit 1
fi
"$python_bin" -m pip install --force-reinstall "${wheels[0]}"
"$release_dir/scripts/install-ibapi.sh" "$python_bin"
"$release_dir/scripts/install-ibc.sh" "$python_bin"
"$python_bin" -I - <<'PY'
import importlib
import importlib.machinery
import pkgutil
from pathlib import Path
import follow_executor
package = Path(follow_executor.__file__).parent
if list(package.rglob('*.py')):
    raise SystemExit('Application source found: extract this release into a fresh directory.')
for name in ['follow_executor', *(m.name for m in pkgutil.walk_packages(
        [str(package)], 'follow_executor.'))]:
    module = importlib.import_module(name)
    if not isinstance(module.__loader__, importlib.machinery.SourcelessFileLoader):
        raise SystemExit(f'{name} did not load from bytecode')
print('Application bytecode and dependencies verified.')
PY
"$release_dir/.venv/bin/follow-executor" --help >/dev/null
unit_dir="$HOME/.config/systemd/user"
mkdir -p "$unit_dir"
cat > "$unit_dir/follow-executor.service" <<EOF
[Unit]
Description=Follow Executor — own-account MNQ/NQ follower
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$release_dir
ExecStart="$release_dir/.venv/bin/follow-executor" run --config "$HOME/.config/follow-executor/executor.json"
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
"$release_dir/.venv/bin/follow-executor" gateway --config "$HOME/.config/follow-executor/executor.json" refresh
sudo loginctl enable-linger "$(id -un)"
echo 'Installed. Continue with docs/SETUP.md or docs/SETUP.zh-CN.md.'
echo 'Trading has not been started. Keep this release directory at its current path.'
