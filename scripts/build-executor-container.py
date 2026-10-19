#!/usr/bin/env python3.12
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Follow Executor contributors
"""Build the executor image without sending checkout sources or secrets to Docker."""

from __future__ import annotations

import argparse
import hashlib
import json
import runpy
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def context_files() -> tuple[str, dict[str, bytes]]:
    if sys.implementation.name != "cpython" or sys.version_info[:2] != (3, 12):
        raise RuntimeError("Build with CPython 3.12")
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    builder = runpy.run_path(str(ROOT / "scripts/build-bytecode.py"))
    files = {
        f"follow_executor-{project['version']}-{builder['TAG']}.whl":
            builder["wheel_bytes"](project),
    }
    for name in ("Dockerfile", "requirements.lock", "build-requirements.lock", "install-api.py"):
        files[name] = (ROOT / "deploy/executor-container" / name).read_bytes()
    for name in ("LICENSE", "NOTICE", "THIRD_PARTY_NOTICES.md"):
        files[name] = (ROOT / name).read_bytes()
    return project["version"], files


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", help="Local image tag; default follow-executor:<version>")
    parser.add_argument("--output", type=Path, default=ROOT / "dist/executor-container")
    args = parser.parse_args()
    version, files = context_files()
    tag = args.tag or f"follow-executor:{version}"
    args.output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="follow-image-") as directory:
        context = Path(directory)
        for name, contents in files.items():
            (context / name).write_bytes(contents)
        subprocess.run([
            "docker", "build", "--pull", "--tag", tag,
            "--label", f"org.opencontainers.image.version={version}",
            "--label", "org.opencontainers.image.licenses=GPL-3.0-or-later",
            str(context),
        ], check=True)
    image_id = subprocess.check_output([
        "docker", "image", "inspect", "--format", "{{.Id}}", tag,
    ], text=True).strip()
    manifest = {"image": tag, "image_id": image_id, "version": version,
                "context_sha256": {name: hashlib.sha256(data).hexdigest()
                                   for name, data in sorted(files.items())}}
    (args.output / "BUILD.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Built {tag}; manifest: {args.output / 'BUILD.json'}")


if __name__ == "__main__":
    main()
