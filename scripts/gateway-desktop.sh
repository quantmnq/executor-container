#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Follow Executor contributors
# Prepare a private graphical login for native IB Gateway on a headless OCI VM.
set -euo pipefail
umask 077
if [[ $EUID -eq 0 ]]; then
    echo 'Run as your Ubuntu login user, without sudo.' >&2
    exit 1
fi
source /etc/os-release
if [[ $ID != ubuntu || $VERSION_ID != 24.04 ]]; then
    echo 'This helper requires Ubuntu 24.04 LTS.' >&2
    exit 1
fi
if [[ $HOME =~ [[:space:]%] ]]; then
    echo 'Use a home directory without whitespace or percent signs.' >&2
    exit 1
fi
if [[ $(uname -m) != aarch64 ]]; then
    echo 'The IBC desktop helper requires ARM64 (aarch64).' >&2
    exit 1
fi
sudo apt-get update
sudo apt-get install -y --no-install-recommends xfce4 xfce4-terminal dbus-x11 tigervnc-standalone-server tigervnc-tools curl ca-certificates fonts-dejavu-core
private_dir="$HOME/.config/follow-executor"
mkdir -p "$private_dir" "$HOME/.config/systemd/user" "$HOME/Downloads"
if [[ ! -f $private_dir/vnc.passwd ]]; then
    tigervncpasswd "$private_dir/vnc.passwd"
fi
chmod 600 "$private_dir/vnc.passwd"
cat > "$private_dir/vnc-start" <<'EOF'
#!/usr/bin/env sh
unset SESSION_MANAGER
unset DBUS_SESSION_BUS_ADDRESS
exec dbus-run-session -- startxfce4
EOF
chmod 700 "$private_dir/vnc-start"
cat > "$HOME/.config/systemd/user/follow-gateway-desktop.service" <<EOF
[Unit]
Description=Private desktop for IB Gateway login

[Service]
Type=simple
ExecStart=/usr/bin/tigervncserver :1 -fg -localhost yes -SecurityTypes VncAuth -rfbauth "$private_dir/vnc.passwd" -geometry 1440x900 -depth 24 -xstartup "$private_dir/vnc-start"
ExecStop=/usr/bin/tigervncserver -kill :1
Restart=on-failure
RestartSec=5
UMask=0077

[Install]
WantedBy=default.target
EOF
installer="$HOME/Downloads/ibgateway-latest-linux-arm.sh"
curl --fail --show-error --location --retry 3 --proto '=https' --proto-redir '=https' --tlsv1.2 \
    'https://download2.interactivebrokers.com/installers/ibgateway/latest-standalone/ibgateway-latest-standalone-linux-arm.sh' \
    -o "$installer.part"
# Native Gateway 10.51 with bundled ARM64 Java 25, reviewed with IBC 3.24.2.
printf '%s  %s\n' 35e48d24c1ea5da56e3aff68aee37a810b3a5771490b95ad6ec8a62266d5c30d "$installer.part" | sha256sum --check --status
mv "$installer.part" "$installer"
systemctl --user daemon-reload
sudo loginctl enable-linger "$(id -un)"
systemctl --user enable --now follow-gateway-desktop.service
sleep 2
systemctl --user is-active follow-gateway-desktop.service
printf '\nFrom your laptop, keep this SSH tunnel open:\n'
printf '  ssh -N -L 5901:127.0.0.1:5901 %s@YOUR_OCI_PUBLIC_IP\n' "$(id -un)"
printf '\nConnect a VNC viewer to localhost:5901, then open its terminal and run:\n'
printf '  sh %q\n' "$installer"
echo 'Complete the installer, then close Gateway and run ./follow gateway configure in SSH.'
echo 'See docs/IBC.md for mobile approval and restart scheduling.'
echo 'The desktop is bound to loopback. Do not open ports 5901, 4001 or 4002 in OCI.'
