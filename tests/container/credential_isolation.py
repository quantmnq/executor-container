# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Follow Executor contributors
"""Probe synthetic secrets through the production launcher's real Docker mounts."""

from __future__ import annotations

import ctypes
import errno
import io
import os
import sys
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from follow_executor.cli import main
from follow_executor.config import load_config
from follow_executor.journal import Journal
from follow_executor.local import default_config_path, default_state_path
from follow_executor.maintenance_state import journal_snapshot


def denied(operation):
    try:
        operation()
    except OSError as exc:
        assert exc.errno in (errno.EACCES, errno.EPERM, errno.EROFS, errno.EBUSY, errno.ENOENT), exc
    else:
        raise AssertionError("Executor accessed or changed a protected Gateway location")


config = default_config_path()
state = default_state_path().parent
gateway = config.parent / "gateway"
backups = state / "maintenance"
assert os.getuid() != 0
assert not Path("/var/run/docker.sock").exists()
for private in (gateway, backups):
    denied(lambda private=private: list(private.iterdir()))
    denied(lambda private=private: (private / "written-by-executor").write_text("must fail"))
    denied(lambda private=private: private.rename(private.with_name(private.name + "-exposed")))
    libc = ctypes.CDLL(None, use_errno=True)
    assert libc.umount2(os.fsencode(private), 0) == -1
    assert ctypes.get_errno() == errno.EPERM

for path in (gateway / "ibc.ini", gateway / "vnc.password",
             backups / "old/config/gateway/ibc.ini", config.parent / "gateway-alias",
             state / "backup-alias"):
    denied(path.read_bytes)
    denied(lambda path=path: Path("/proc/self/root" + str(path)).read_bytes())

action = sys.argv[1]
output = io.StringIO()
with redirect_stdout(output):
    if action == "configure":
        with (patch("builtins.input", side_effect=["paper", "DU1234567", "MNQ", "1"]),
              patch("getpass.getpass", return_value="isolated-fixture-token")):
            assert main(["configure", "--config", str(config)]) == 0
    elif action == "settings":
        # Only the external broker-flat check is replaced. Real CLI locks,
        # atomic configuration replacement and journal identity update still run.
        with patch("follow_executor.setup.require_flat"):
            assert main(["settings", "--quantity", "2", "--config", str(config)]) == 0
    elif action == "discord":
        reply = {"ready": True, "health_notifications": True,
                 "position_notifications": True, "link_id": "a" * 32}
        with patch("follow_executor.notifications.request", return_value=reply):
            assert main(["discord", "enable", "--config", str(config)]) == 0

saved = load_config(config)
assert saved.token() == "isolated-fixture-token"
assert saved.quantity == (1 if action == "configure" else 2)
assert journal_snapshot(saved)["halt_present"] is False
journal = Journal(saved.journal_path)
try:
    journal.log("isolation_probe", {"action": action})
finally:
    journal.close()
print("PASS: protected credential reads/writes denied; executor config/token/journal usable")
