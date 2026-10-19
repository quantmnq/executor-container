# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Follow Executor contributors
"""Follower setup and verified, flat-only changes of instrument and size."""

from __future__ import annotations

import getpass
import json
import os
from dataclasses import replace
from pathlib import Path

from .config import ConfigError, ExecutorConfig, load_config, parse_config
from .journal import Journal
from .local import (
    bind_settings,
    default_state_path,
    exclusive,
    private_write,
    settings_identity,
)

DEFAULT_RELAY = "https://relay.quantmnq.com"
DEFAULT_STREAM = "sessioncycle.mnq"
DEFAULT_KEY = "zesvLFF3vT/hPtfal4i+m6K35v+cO9x4+jOXFLH6Xp4="


def ask(label: str, default: str = "", choices: tuple[str, ...] = ()) -> str:
    while True:
        answer = input(f"{label}{f' [{default}]' if default else ''}: ").strip() or default
        if answer and (not choices or answer in choices):
            return answer
        print(f"Enter {' / '.join(choices) if choices else 'a value'}.")


def ask_quantity(default: int, ceiling: int) -> int:
    while True:
        value = ask(f"Number of contracts (1–{ceiling})", str(default))
        if value.isdecimal() and 1 <= int(value) <= ceiling:
            return int(value)
        print(f"Enter a whole number from 1 to {ceiling}.")


def initial_config(path: Path, *, advanced: bool = False) -> int:
    if path.exists():
        current = load_config(path)
        print(f"Existing {current.ibkr.account_type} setup: {current.quantity} {current.root}.")
        root = ask("Instrument", current.root, ("MNQ", "NQ"))
        quantity = ask_quantity(current.quantity, current.max_quantity)
        return change_settings(path, root=root, quantity=quantity)

    print("Follow Executor setup — IBKR passwords stay in Gateway/IBC on your VM.")
    mode = ask("Account mode", "paper", ("paper", "live"))
    account = ask("IBKR account ID (for example DU1234567)").upper()
    root = ask("Instrument", "MNQ", ("MNQ", "NQ"))
    quantity = ask_quantity(1, 10)
    if mode == "live" and input(
        f"Type LIVE {account} to configure real-money trading: "
    ).strip() != f"LIVE {account}":
        raise ConfigError("live setup cancelled; no files changed")
    raw = {
        "relay_url": DEFAULT_RELAY,
        "stream": DEFAULT_STREAM,
        "leader_public_key": DEFAULT_KEY,
        "token_path": str(path.parent / "relay.token"),
        "journal_path": str(default_state_path()),
        "ibkr": {
            "host": "127.0.0.1", "port": 4002 if mode == "paper" else 4001,
            "client_id": 71, "account": account, "account_type": mode,
        },
        "instrument": {"root": root, "quantity": quantity},
        "risk": {"max_quantity": 10, "max_margin_fraction": 0.5,
                 "max_entry_slippage_points": 10, "max_stop_risk_usd": None},
        "feed": {"send_acks": True},
    }
    if advanced:
        raw["relay_url"] = ask("Relay URL", DEFAULT_RELAY)
        raw["stream"] = ask("Stream", DEFAULT_STREAM)
        raw["leader_public_key"] = ask("Leader public key", DEFAULT_KEY)
        raw["ibkr"]["host"] = ask("IB Gateway host", "127.0.0.1")
        raw["ibkr"]["port"] = int(ask("IB Gateway API port", str(raw["ibkr"]["port"])))
        raw["ibkr"]["client_id"] = int(ask("IB Gateway client ID", "71"))
    config = parse_config(raw)
    token = getpass.getpass("Personal relay token (hidden): ").strip()
    if not token or any(c.isspace() for c in token):
        raise ConfigError("a nonempty relay token without whitespace is required")
    with exclusive(config.journal_path.with_suffix(config.journal_path.suffix + ".lock")):
        journal = Journal(config.journal_path)
        try:
            bind_settings(journal, config)
        finally:
            journal.close()
        private_write(config.token_path, token + "\n")
        private_write(path, json.dumps(raw, indent=2) + "\n")
    print(f"Saved {quantity} {root} in {mode} mode to {path}.")
    launcher = os.environ.get("FOLLOW_EXECUTOR_LAUNCHER", "./follow")
    print(f"Log in to IB Gateway, then run '{launcher} check' and '{launcher} start'.")
    return 0


def require_flat(config: ExecutorConfig) -> None:
    """Wait for IBKR snapshot-end callbacks; an empty early cache is not proof."""
    from .ibkr import IBKRBroker

    broker = IBKRBroker(config.ibkr, config.root)
    try:
        broker.connect()
        if config.ibkr.account not in broker.managed_accounts:
            raise ConfigError("the configured account is not managed by this Gateway login")
        broker.refresh()
        broker.wait_for_snapshot()
        state = broker.state()
        if any(state.positions.values()) or any(o.working for o in state.orders.values()):
            raise ConfigError(
                f"{config.root} has positions or working orders; settings were not changed. "
                "Wait until flat and all orders are completed/cancelled."
            )
    finally:
        broker.disconnect()


def change_settings(path: Path, *, root: str | None, quantity: int | None) -> int:
    old = load_config(path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["instrument"] = {"root": root or old.root,
                         "quantity": old.quantity if quantity is None else quantity}
    new = parse_config(raw)
    if (new.root, new.quantity) == (old.root, old.quantity):
        print(f"Already configured for {old.quantity} {old.root}; no changes.")
        return 0
    with exclusive(old.journal_path.with_suffix(old.journal_path.suffix + ".lock")):
        journal = Journal(old.journal_path)
        try:
            bind_settings(journal, old)
            if journal.expected_positions():
                raise ConfigError("the journal records an open position; wait until flat")
            if journal.halt_reason():
                raise ConfigError("resolve the executor halt before changing settings")
            require_flat(old)
            if new.root != old.root:
                require_flat(replace(old, root=new.root))
            # Preserve trade history: changing size must never re-enter a finished trade.
            private_write(path, json.dumps(raw, indent=2) + "\n")
            journal.set_state("settings_identity", settings_identity(new))
            journal.log("settings_changed", {"root": new.root, "quantity": new.quantity})
        finally:
            journal.close()
    launcher = os.environ.get("FOLLOW_EXECUTOR_LAUNCHER", "./follow")
    print(f"Saved {new.quantity} {new.root}. Run '{launcher} start' to apply it.")
    return 0
