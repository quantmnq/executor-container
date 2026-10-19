# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Follow Executor contributors
"""Verify retained customer releases before maintenance; stdlib only."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import zipfile
from pathlib import Path

from .config import ConfigError


def verify_release(root: Path) -> dict:
    root = root.resolve()
    checksums = {}
    for line in (root / "SHA256SUMS").read_text().splitlines():
        digest, name = line.split("  ", 1)
        path = root / name
        if name in checksums or path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ConfigError("Invalid release checksum list.")
        with path.open("rb") as handle:
            if hashlib.file_digest(handle, "sha256").hexdigest() != digest:
                raise ConfigError("Release verification failed; use the original customer archive.")
        checksums[name] = digest
    meta = json.loads((root / "RELEASE.json").read_text())
    required = {"RELEASE.json", "follow-stack", "follow-container", "scripts/stack-bootstrap.py", meta["wheel"]}
    image = meta["executor_image"]
    if (not required.issubset(checksums) or meta["bytecode_magic"] != importlib.util.MAGIC_NUMBER.hex()
            or checksums[meta["wheel"]] != meta["wheel_sha256"]
            or checksums.get(image["archive"]) != image["archive_sha256"]):
        raise ConfigError("Incomplete or incompatible container release.")
    with zipfile.ZipFile(root / meta["wheel"]) as wheel:
        # Conservative compatibility: no journal/configuration or Gateway code
        # changes are migrated automatically. This also supports earlier 0.1.7 kits.
        meta["compatibility"] = {module: hashlib.sha256(wheel.read(f"follow_executor/{module}.pyc")).hexdigest()
                                 for module in ("journal", "config", "local", "gateway", "gateway_docker")}
    return meta
