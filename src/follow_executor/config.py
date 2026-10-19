# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Follow Executor contributors
"""Strict follower-executor configuration."""

from __future__ import annotations

import base64
import binascii
import ipaddress
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .broker import MULTIPLIERS

STREAM_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
HARD_MAX_QUANTITY = 100


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class IBKRSettings:
    host: str
    port: int
    client_id: int
    account: str
    account_type: str  # paper or live
    timeout_seconds: float


@dataclass(frozen=True)
class ExecutorConfig:
    relay_url: str
    stream: str
    leader_public_key: str
    token_path: Path
    journal_path: Path
    ca_file: Path | None
    ibkr: IBKRSettings
    root: str
    quantity: int
    max_quantity: int
    max_entry_slippage_points: float
    max_margin_fraction: float
    max_stop_risk_usd: float | None
    margin_check_max_age_seconds: float
    heartbeat_timeout_seconds: float
    clock_exit_grace_seconds: float
    send_acks: bool
    discord_link_id: str | None = None

    @property
    def multiplier(self) -> float:
        return MULTIPLIERS[self.root]

    def token(self) -> str:
        token = self.token_path.read_text(encoding="utf-8").strip()
        if not token:
            raise ConfigError(f"{self.token_path} is empty")
        return token


def _section(raw: dict[str, Any], name: str) -> dict[str, Any]:
    value = raw.get(name, {})
    if not isinstance(value, dict):
        raise ConfigError(f"{name} must be an object")
    return value


def _absolute(value: Any, name: str) -> Path:
    if not isinstance(value, str) or not Path(value).is_absolute():
        raise ConfigError(f"{name} must be an absolute path")
    return Path(value)


def _number(section: dict[str, Any], key: str, default: float, low: float, high: float) -> float:
    value = section.get(key, default)
    if type(value) not in (int, float) or not low <= value <= high:
        raise ConfigError(f"{key} must be a number from {low} to {high}")
    return float(value)


def _integer(section: dict[str, Any], key: str, default: int | None, low: int, high: int) -> int:
    value = section.get(key, default)
    if type(value) is not int or not low <= value <= high:
        raise ConfigError(f"{key} must be an integer from {low} to {high}")
    return value


def _relay_url(value: Any) -> str:
    if not isinstance(value, str):
        raise ConfigError("relay_url must be a string")
    parsed = urlparse(value)
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ConfigError("relay_url must not contain credentials, a query or a fragment")
    if parsed.scheme == "https" and parsed.hostname:
        return value.rstrip("/")
    if parsed.scheme == "http" and parsed.hostname:
        try:
            if ipaddress.ip_address(parsed.hostname).is_loopback:
                return value.rstrip("/")
        except ValueError:
            pass
    raise ConfigError("relay_url must be https (plain http only to a loopback address)")


def _public_key(value: Any) -> str:
    try:
        raw = base64.b64decode(str(value), validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ConfigError("leader_public_key must be base64") from exc
    if len(raw) != 32:
        raise ConfigError("leader_public_key must be a 32-byte Ed25519 key")
    return str(value)


def _ibkr(section: dict[str, Any]) -> IBKRSettings:
    account = section.get("account")
    if not isinstance(account, str) or not re.fullmatch(r"[A-Z]{1,3}\d{4,10}", account):
        raise ConfigError("ibkr.account must be an IBKR account id, such as DU1234567")
    account_type = section.get("account_type")
    if account_type not in ("paper", "live"):
        raise ConfigError("ibkr.account_type must be paper or live")
    # IBKR paper accounts start with D (DU, DF); live ones do not.
    if (account_type == "paper") != account.startswith("D"):
        raise ConfigError(f"ibkr.account {account} does not look like a {account_type} account")
    host = section.get("host", "127.0.0.1")
    if not isinstance(host, str) or not host:
        raise ConfigError("ibkr.host must be a host name")
    return IBKRSettings(
        host=host,
        port=_integer(section, "port", None, 1, 65535),
        client_id=_integer(section, "client_id", 71, 1, 32767),
        account=account,
        account_type=account_type,
        timeout_seconds=_number(section, "timeout_seconds", 15, 2, 120),
    )


def load_config(path: str | Path) -> ExecutorConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return parse_config(raw)


def parse_config(raw: Any) -> ExecutorConfig:
    if not isinstance(raw, dict):
        raise ConfigError("the configuration must be a JSON object")
    known = {"relay_url", "stream", "leader_public_key", "token_path", "journal_path",
             "ca_file", "ibkr", "instrument", "risk", "feed", "notifications"}
    unknown = sorted(set(raw) - known)
    if unknown:
        raise ConfigError(f"unknown configuration keys: {', '.join(unknown)}")
    stream = raw.get("stream")
    if not isinstance(stream, str) or not STREAM_PATTERN.match(stream):
        raise ConfigError("stream must be a stream name such as sessioncycle.mnq")

    instrument = _section(raw, "instrument")
    root = instrument.get("root")
    if root not in MULTIPLIERS:
        raise ConfigError("instrument.root must be NQ or MNQ")
    risk = _section(raw, "risk")
    max_quantity = _integer(risk, "max_quantity", 10, 1, HARD_MAX_QUANTITY)
    quantity = _integer(instrument, "quantity", None, 1, max_quantity)
    stop_risk = risk.get("max_stop_risk_usd")
    if stop_risk is not None and (
        type(stop_risk) not in (int, float) or not math.isfinite(stop_risk) or stop_risk <= 0
    ):
        raise ConfigError("max_stop_risk_usd must be a positive number or null")
    feed = _section(raw, "feed")
    acks = feed.get("send_acks", True)
    if type(acks) is not bool:
        raise ConfigError("feed.send_acks must be true or false")
    ca_file = raw.get("ca_file")
    notifications = _section(raw, "notifications")
    if notifications.keys() - {"discord_link_id"}:
        raise ConfigError("unknown notifications setting")
    link_id = notifications.get("discord_link_id")
    if link_id is not None and (not isinstance(link_id, str)
                                or not re.fullmatch(r"[a-f0-9]{32}", link_id)):
        raise ConfigError("notifications.discord_link_id must come from Discord pairing")

    return ExecutorConfig(
        relay_url=_relay_url(raw.get("relay_url")),
        stream=stream,
        leader_public_key=_public_key(raw.get("leader_public_key")),
        token_path=_absolute(raw.get("token_path"), "token_path"),
        journal_path=_absolute(raw.get("journal_path"), "journal_path"),
        ca_file=None if ca_file is None else _absolute(ca_file, "ca_file"),
        ibkr=_ibkr(_section(raw, "ibkr")),
        root=root,
        quantity=quantity,
        max_quantity=max_quantity,
        max_entry_slippage_points=_number(risk, "max_entry_slippage_points", 10.0, 0.25, 500.0),
        max_margin_fraction=_number(risk, "max_margin_fraction", 0.5, 0.05, 1.0),
        max_stop_risk_usd=None if stop_risk is None else float(stop_risk),
        margin_check_max_age_seconds=_number(risk, "margin_check_max_age_seconds", 900, 60, 86400),
        heartbeat_timeout_seconds=_number(feed, "heartbeat_timeout_seconds", 30, 10, 600),
        clock_exit_grace_seconds=_number(feed, "clock_exit_grace_seconds", 30, 0, 300),
        send_acks=acks,
        discord_link_id=link_id,
    )
