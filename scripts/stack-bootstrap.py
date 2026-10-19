# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Follow Executor contributors
"""Verify a customer kit and load its controller without installing dependencies."""

import hashlib
import importlib.util
import json
import sys
from pathlib import Path


def digest(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def main():
    release = Path(__file__).resolve().parents[1]
    try:
        if sys.implementation.name != "cpython" or sys.version_info[:2] != (3, 12):
            raise ValueError("Use Ubuntu 24.04's CPython 3.12.")
        if (release / "RELEASE.json").exists():
            checksums = {}
            for line in (release / "SHA256SUMS").read_text().splitlines():
                expected, name = line.split("  ", 1)
                path = release / name
                if (path.is_symlink() or not path.resolve().is_relative_to(release)
                        or name in checksums or digest(path) != expected):
                    raise ValueError("Release verification failed; obtain the original customer archive.")
                checksums[name] = expected
            metadata = json.loads((release / "RELEASE.json").read_text())
            required = {"RELEASE.json", "follow-stack", "follow-container",
                        "scripts/stack-bootstrap.py", "scripts/install-docker.sh", metadata["wheel"]}
            if not required.issubset(checksums):
                raise ValueError("Incomplete release checksum list.")
            if (metadata["bytecode_magic"] != importlib.util.MAGIC_NUMBER.hex()
                    or checksums[metadata["wheel"]] != metadata["wheel_sha256"]):
                raise ValueError("Incompatible or damaged bytecode wheel.")
            image = metadata.get("executor_image")
            if image and checksums.get(image["archive"]) != image["archive_sha256"]:
                raise ValueError("Executor image archive is not covered by release checksums.")
            sys.path.insert(0, str(release / metadata["wheel"]))
        elif (release / "pyproject.toml").is_file() and (release / "src/follow_executor").is_dir():
            # Maintainer checkout only. Customer archives always use verified bytecode.
            sys.path.insert(0, str(release / "src"))
        else:
            raise ValueError("Missing RELEASE.json; use an intact customer kit.")
        from follow_executor.stack import main as stack_main

        return stack_main(release)
    except (OSError, ValueError, KeyError, ImportError) as exc:
        print(f"follow-stack: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
