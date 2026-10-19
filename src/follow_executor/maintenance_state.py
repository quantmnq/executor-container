# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Follow Executor contributors
"""Read-only journal inspection and consistent private maintenance backups."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import closing

from .config import ConfigError
from .local import settings_identity


def open_readonly(path):
    if not path.is_file() or path.is_symlink():
        raise ConfigError("An existing regular journal is required; maintenance never initializes one.")
    return sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)


def journal_snapshot(config) -> dict:
    with closing(open_readonly(config.journal_path)) as db:
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ConfigError("Journal integrity check failed; maintenance was refused.")
        state = dict(db.execute("SELECT key, value FROM state"))
        if state.get("settings_identity") != settings_identity(config):
            raise ConfigError("Journal identity does not match configuration; maintenance was refused.")
        baseline = json.loads(state.get("baseline", '{"positions":{},"after_rowid":0}'))
        positions = {int(k): int(v) for k, v in baseline["positions"].items()}
        for con_id, side, quantity in db.execute(
            "SELECT con_id, side, quantity FROM executions WHERE rowid > ?", (baseline["after_rowid"],),
        ):
            positions[con_id] = positions.get(con_id, 0) + quantity * (1 if side == "BOT" else -1)
        if any(positions.values()):
            raise ConfigError("The journal records an open position; wait until flat before maintenance.")
        contents = "\n".join(db.iterdump())
        # Execution rowids participate in the baseline and must also be preserved.
        contents += repr(list(db.execute("SELECT rowid, exec_id FROM executions ORDER BY rowid")))
        return {"flat": True, "journal_sha256": hashlib.sha256(contents.encode()).hexdigest(),
                "halt_present": bool(state.get("halt")), "integrity": "ok"}


def backup_journal(config, destination) -> None:
    destination.touch(mode=0o600, exist_ok=False)
    with closing(open_readonly(config.journal_path)) as source, closing(sqlite3.connect(destination)) as target:
        source.backup(target)
        if target.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ConfigError("Journal backup verification failed.")
