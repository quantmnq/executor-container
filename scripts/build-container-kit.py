#!/usr/bin/env python3.12
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Follow Executor contributors
"""Bundle an already-built ARM64 executor image and its matching customer wizard."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import runpy
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", type=Path, required=True, help="BUILD.json from build-executor-container.py")
    parser.add_argument("--output", type=Path, default=ROOT / "dist/container-kit")
    parser.add_argument("--third-party", type=Path, required=True,
                        help="SOURCES.json from collect-third-party-source.py")
    args = parser.parse_args()
    manifest = json.loads(args.build.read_text())
    image_id = manifest["image_id"]
    if not re.fullmatch(r"sha256:[a-f0-9]{64}", image_id):
        raise ValueError("Invalid executor image ID")
    builder = runpy.run_path(str(ROOT / "scripts/build-bytecode.py"))
    context = runpy.run_path(str(ROOT / "scripts/build-executor-container.py"))["context_files"]()
    version, files = context
    hashes = {name: hashlib.sha256(value).hexdigest() for name, value in files.items()}
    if manifest["context_sha256"] != hashes or manifest["version"] != version:
        raise ValueError("Build inputs changed. Rebuild the executor image before bundling.")
    actual = subprocess.check_output([
        "docker", "image", "inspect", "--format", "{{.Id}} {{.Os}}/{{.Architecture}}", image_id,
    ], text=True).strip()
    if actual != f"{image_id} linux/arm64":
        raise ValueError("Customer bundle requires the matching Linux ARM64 image")
    dependencies = json.loads(args.third_party.read_text())
    dependency_archive = args.third_party.parent / dependencies["archive"]
    if hashlib.sha256(dependency_archive.read_bytes()).hexdigest() != dependencies["sha256"]:
        raise ValueError("Dependency source archive checksum mismatch")
    # Compare actual installed versions, excluding only this application's version.
    inventory_code = "import importlib.metadata as m,json; print(json.dumps(sorted((d.metadata['Name'],d.version) for d in m.distributions() if d.metadata['Name'] != 'follow-executor')))"
    packages = json.loads(subprocess.check_output([
        "docker", "run", "--rm", "--network", "none", "--entrypoint", "python",
        image_id, "-c", inventory_code,
    ], text=True))
    debian = subprocess.check_output([
        "docker", "run", "--rm", "--network", "none", "--entrypoint", "dpkg-query",
        image_id, "-W", "-f=${binary:Package}\t${source:Package}\t${source:Version}\n",
    ], text=True)
    debian_packages = [dict(zip(("binary", "source", "version"), row.split("\t")))
                       for row in debian.splitlines()]
    python_runtime = subprocess.check_output([
        "docker", "run", "--rm", "--network", "none", "--entrypoint", "python",
        image_id, "-c", "import sys,os; print(sys.version.split()[0],os.environ['PYTHON_SHA256'])",
    ], text=True).strip()
    expected_python = (dependencies["inventory"]["python"] + " "
                       + dependencies["inventory"]["python_sha256"])
    if (packages != dependencies["inventory"]["python_packages"]
            or debian_packages != dependencies["inventory"]["debian"]
            or python_runtime != expected_python):
        raise ValueError("Dependency sources do not match installed image packages")
    args.output.mkdir(parents=True, exist_ok=True)
    source_name = f"follow-executor-{version}-dependencies.tar.gz"
    shutil.copyfile(dependency_archive, args.output / source_name)
    with tempfile.TemporaryDirectory(prefix="follow-stack-bundle-") as directory:
        archive = Path(directory) / "executor.tar.gz"
        with subprocess.Popen(["docker", "save", image_id], stdout=subprocess.PIPE) as process:
            with archive.open("wb") as raw, gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as compressed:
                shutil.copyfileobj(process.stdout, compressed)
            if process.wait():
                raise RuntimeError("Could not export executor image")
        print(builder["build"](args.output.resolve(), executor_image={
            "id": image_id, "platform": "linux/arm64",
            "wheel_sha256": hashes[f"follow_executor-{version}-cp312-none-any.whl"],
        }, image_archive=archive, third_party_source={
            "archive": source_name, "sha256": dependencies["sha256"],
        }))


if __name__ == "__main__":
    main()
