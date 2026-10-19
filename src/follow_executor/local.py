# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Follow Executor contributors
"""Local process locking and private, atomic configuration writes."""

from __future__ import annotations

import fcntl
import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path

from .config import ConfigError, ExecutorConfig


def default_config_path() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "follow-executor" / "executor.json"


def default_state_path() -> Path:
    base = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state"))
    return base / "follow-executor" / "executor.sqlite3"


@contextmanager
def exclusive(path: Path):
    """Hold an advisory lock. Never unlink it: waiters may still have it open."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ConfigError(
                "the executor or another setup/check command is running; "
                "stop the service before changing settings or checking IBKR"
            ) from exc
        yield
    finally:
        os.close(fd)


def private_write(path: Path, contents: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(contents)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def settings_identity(config: ExecutorConfig) -> str:
    return json.dumps({
        "account": config.ibkr.account,
        "account_type": config.ibkr.account_type,
        "client_id": config.ibkr.client_id,
        "host": config.ibkr.host,
        "port": config.ibkr.port,
        "root": config.root,
        "quantity": config.quantity,
        "stream": config.stream,
        "leader_public_key": config.leader_public_key,
    }, sort_keys=True)


def bind_settings(journal, config: ExecutorConfig) -> None:
    identity = settings_identity(config)
    previous = journal.get_state("settings_identity")
    if previous is not None and previous != identity:
        raise ConfigError(
            "account, connection, stream or instrument settings changed outside setup; "
            "restore the previous config and use 'settings' while flat"
        )
    journal.set_state("settings_identity", identity)
