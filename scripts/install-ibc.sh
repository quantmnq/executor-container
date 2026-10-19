#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Follow Executor contributors
# Download upstream IBC separately; credentials never belong in the release tree.
set -euo pipefail
umask 077
release_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
python_bin=${1:-"$release_dir/.venv/bin/python"}
ibc_dir="$release_dir/vendor/ibc-3.24.2"
ibc_tmp=$(mktemp -d)
trap 'rm -rf -- "$ibc_tmp"' EXIT
curl --fail --silent --show-error --location --retry 3 --proto '=https' --proto-redir '=https' \
    https://github.com/IbcAlpha/IBC/releases/download/3.24.2/IBCLinux-3.24.2.zip -o "$ibc_tmp/ibc.zip"
printf '%s  %s\n' cc097ca1dfa75413a5fbe02e4743050af15f3308eb6a97c769b3cff9850c80c5 "$ibc_tmp/ibc.zip" | sha256sum --check --status
mkdir -p "$ibc_dir"
"$python_bin" -m zipfile -e "$ibc_tmp/ibc.zip" "$ibc_dir"
chmod 700 "$ibc_dir"/*.sh "$ibc_dir"/scripts/*.sh
echo 'IBC 3.24.2 installed. Configure it with ./follow gateway configure after installing Gateway.'
