#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Follow Executor contributors
# Official API only; no unrelated PyPI package and no vendored IBKR source.
set -euo pipefail
repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
python_bin=${1:-"$repo_dir/.venv/bin/python"}
api_url=https://interactivebrokers.github.io/downloads/twsapi_macunix.1050.02.zip
api_sha256=673129e5cba58c4d77bc40647265f84ea42f605eccf88fa4c1221d62d12454f3
api_tmp=$(mktemp -d)
trap 'rm -rf -- "$api_tmp"' EXIT
curl --fail --silent --show-error --location --retry 3 --proto '=https' --proto-redir '=https' --tlsv1.2 "$api_url" -o "$api_tmp/api.zip"
printf '%s  %s\n' "$api_sha256" "$api_tmp/api.zip" | sha256sum --check --status
"$python_bin" -m zipfile -e "$api_tmp/api.zip" "$api_tmp/api"
"$python_bin" -m pip install "$api_tmp/api/IBJts/source/pythonclient"
"$python_bin" -c 'from ibapi.client import EClient; from ibapi.order_cancel import OrderCancel; print("Official IBKR API installed")'
