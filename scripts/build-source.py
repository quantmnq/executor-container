#!/usr/bin/env python3.12
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Follow Executor contributors
"""Export only reviewed public files, without Git history or machine state."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import tarfile
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def public_files() -> dict[str, bytes]:
    names = (ROOT / "deploy/public-files.txt").read_text().splitlines()
    files = {}
    for name in names:
        if not name or name.startswith("#"):
            continue
        path = ROOT / name
        if (name in files or Path(name).is_absolute() or ".." in Path(name).parts
                or any(p.startswith(".") and p not in (".github", ".gitignore")
                       for p in Path(name).parts)
                or path.is_symlink() or not path.is_file()
                or not path.resolve().is_relative_to(ROOT.resolve())):
            raise ValueError(f"Invalid public export path: {name}")
        files[name] = path.read_bytes()
    # Missing modules must not produce an apparently complete source release.
    modules = {p.relative_to(ROOT).as_posix()
               for p in (ROOT / "src/follow_executor").rglob("*.py")}
    if not modules.issubset(files):
        raise ValueError("Public allowlist omits application modules")
    return files


def source_bytes(project: dict) -> bytes:
    files = public_files()
    manifest = {"version": project["version"], "license": "GPL-3.0-or-later",
                "files": {name: hashlib.sha256(data).hexdigest()
                          for name, data in sorted(files.items())}}
    files["SOURCE.json"] = (json.dumps(manifest, indent=2) + "\n").encode()
    output = io.BytesIO()
    with (
        gzip.GzipFile(filename="", mode="wb", fileobj=output, mtime=0) as compressed,
        tarfile.open(fileobj=compressed, mode="w") as archive,
    ):
        for name, data in sorted(files.items()):
            item = tarfile.TarInfo(f"follow-executor-{project['version']}-source/{name}")
            item.size = len(data)
            item.mode = 0o755 if data.startswith(b"#!") else 0o644
            archive.addfile(item, io.BytesIO(data))
    return output.getvalue()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist/source")
    parser.add_argument("--export", type=Path, help="Create a NEW directory for the public Git repository")
    args = parser.parse_args()
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    data = source_bytes(project)
    args.output.mkdir(parents=True, exist_ok=True)
    path = args.output / f"follow-executor-{project['version']}-source.tar.gz"
    path.write_bytes(data)
    path.with_suffix(".gz.sha256").write_text(f"{hashlib.sha256(data).hexdigest()}  {path.name}\n")
    if args.export:
        args.export.mkdir(parents=True, exist_ok=False)
        for name, content in public_files().items():
            target = args.export / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            target.chmod(0o755 if content.startswith(b"#!") else 0o644)
    print(path)


if __name__ == "__main__":
    main()
