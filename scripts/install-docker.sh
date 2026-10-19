#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Follow Executor contributors
# Container setup helper. Does not start Gateway or the executor.
set -euo pipefail
umask 077
if [[ $EUID -eq 0 ]]; then
    echo 'Run as your Ubuntu login user, without sudo.' >&2
    exit 1
fi
source /etc/os-release
if [[ $ID != ubuntu || $VERSION_ID != 24.04 || $(uname -m) != aarch64 ]]; then
    echo 'Auto Quant container setup requires Ubuntu 24.04 ARM64.' >&2
    exit 1
fi
for service in follow-executor.service follow-gateway.service; do
    state=$(systemctl --user show "$service" -p ActiveState --value)
    case "$state" in
        inactive|failed) ;;
        *) echo "Stop $service while flat before installing Docker." >&2; exit 1 ;;
    esac
done
if ! command -v docker >/dev/null; then
    # Do not silently replace an existing container runtime or its packages.
    for package in docker.io docker-compose docker-compose-v2 podman-docker containerd runc; do
        if dpkg-query -W -f='${Status}' "$package" 2>/dev/null | grep -q '^install ok installed$'; then
            echo "Existing $package package found. Follow Docker's Ubuntu installation guide before continuing." >&2
            exit 1
        fi
    done
    sudo apt-get update
    sudo apt-get install -y ca-certificates curl
    docker_tmp=$(mktemp -d)
    trap 'rm -rf "$docker_tmp"' EXIT
    curl --fail --show-error --location --proto '=https' --proto-redir '=https' \
        https://download.docker.com/linux/ubuntu/gpg -o "$docker_tmp/docker.asc"
    sudo install -m 0755 -d /etc/apt/keyrings
    sudo install -m 0644 "$docker_tmp/docker.asc" /etc/apt/keyrings/docker.asc
    cat > "$docker_tmp/docker.sources" <<'EOF'
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: noble
Components: stable
Architectures: arm64
Signed-By: /etc/apt/keyrings/docker.asc
EOF
    sudo install -m 0644 "$docker_tmp/docker.sources" /etc/apt/sources.list.d/docker.sources
    sudo apt-get update
    sudo apt-get install -y docker-ce docker-ce-cli containerd.io
fi
sudo systemctl enable --now docker.service
sudo groupadd -f docker
if ! id -nG "$(id -un)" | tr ' ' '\n' | grep -qx docker; then
    # Docker group members can administer the VM. Use a dedicated customer VM.
    sudo usermod -aG docker "$(id -un)"
fi
sudo loginctl enable-linger "$(id -un)"
echo 'Docker is installed. Gateway and trading have not been started.'
echo 'After first installation, reboot the VM once to refresh login and user-service group membership.'
echo 'Then reconnect and return to the extracted installation directory.'
echo 'Combined kit: rerun ./follow-stack setup (see docs/CONTAINER_SETUP.md).'
echo 'Separate Gateway kit: run ./follow gateway configure --backend docker --vnc (see docs/GATEWAY_DOCKER.md).'
