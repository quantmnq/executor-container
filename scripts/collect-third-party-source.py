#!/usr/bin/env python3.12
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Follow Executor contributors
"""Retain dependency source and notices for the exact executor image; no broker access."""

from __future__ import annotations

import argparse
import ast
import gzip
import hashlib
import json
import shutil
import subprocess
import tarfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Runs in a disposable image container with only the output directory mounted.
COLLECT = r'''
import importlib.metadata as metadata
import json, os, pathlib, shutil, subprocess, sys
out = pathlib.Path('/out')
fmt = '${binary:Package}\t${source:Package}\t${source:Version}\n'
rows = subprocess.check_output(['dpkg-query','-W','-f='+fmt],text=True)
packages = [dict(zip(('binary','source','version'),row.split('\t')))
            for row in rows.splitlines()]
inventory = {'debian':packages, 'python':sys.version.split()[0],
             'python_sha256':os.environ['PYTHON_SHA256'],
             'python_packages':sorted((d.metadata['Name'],d.version)
                 for d in metadata.distributions() if d.metadata['Name'] != 'follow-executor')}
(out/'INVENTORY.json').write_text(json.dumps(inventory,indent=2)+'\n')
notices = out/'notices'
notices.mkdir(exist_ok=True)
for package in packages:
    path = pathlib.Path('/usr/share/doc')/package['binary'].split(':')[0]/'copyright'
    if path.is_file():
        shutil.copyfile(path,notices/(package['binary'].replace(':','_')+'.copyright'))
shutil.copytree('/usr/share/common-licenses',notices/'common-licenses',dirs_exist_ok=True)
for d in metadata.distributions():
    if d.metadata['Name'] == 'follow-executor':
        continue
    for f in d.files or ():
        if any(word in str(f).lower() for word in ('license','copying','notice')):
            src = d.locate_file(f)
            if src.is_file():
                target=notices/'python'/d.metadata['Name']/str(f)
                target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(src,target)
for path in pathlib.Path('/etc/apt/sources.list.d').glob('*.sources'):
    path.write_text(path.read_text().replace('Types: deb\n','Types: deb deb-src\n'))
subprocess.run(['apt-get','update','-qq'],check=True)
debian = out/'debian'
debian.mkdir(exist_ok=True)
specs=sorted({p['source']+'='+p['version'] for p in packages})
subprocess.run(['apt-get','source','--download-only','--only-source',*specs],cwd=debian,check=True)
'''


def download(url: str, target: Path, digest: str | None = None) -> dict:
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        with urllib.request.urlopen(url, timeout=120) as response, target.open("wb") as output:
            shutil.copyfileobj(response, output)
    actual = hashlib.sha256(target.read_bytes()).hexdigest()
    if digest is not None and actual != digest:
        target.unlink()
        raise ValueError(f"Source checksum mismatch: {target.name}")
    return {"url": url, "sha256": actual, "file": target.name}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "dist/third-party")
    args = parser.parse_args()
    args.output = args.output.resolve()
    tree = args.output / "third-party-source"
    tree.mkdir(parents=True, exist_ok=True)
    if not (tree / "DEBIAN_COMPLETE").exists():
        subprocess.run([
            "docker", "run", "--rm", "--user", "0:0", "--entrypoint", "python",
            "--mount", f"type=bind,src={tree},dst=/out", args.image, "-c", COLLECT,
        ], check=True)
        # Root-owned downloaded files are readable; this marker is written by the builder.
        (tree / "DEBIAN_COMPLETE").write_text("apt-get source completed for every installed Debian source package\n")
    inventory = json.loads((tree / "INVENTORY.json").read_text())
    records = {}
    api = {}
    for node in ast.parse((ROOT / "deploy/executor-container/install-api.py").read_text()).body:
        if (isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id in ("URL", "SHA256")):
            api[node.targets[0].id] = ast.literal_eval(node.value)
    records["ibapi"] = download(api["URL"], tree / "ibkr/twsapi_macunix.1050.02.zip", api["SHA256"])
    version = inventory["python"]
    records["CPython"] = download(f"https://www.python.org/ftp/python/{version}/Python-{version}.tar.xz",
                                  tree / f"python/Python-{version}.tar.xz", inventory["python_sha256"])
    for name, version in inventory["python_packages"]:
        if name == "ibapi":
            continue
        with urllib.request.urlopen(f"https://pypi.org/pypi/{name}/{version}/json", timeout=60) as response:
            release = json.load(response)
        source = next(item for item in release["urls"] if item["packagetype"] == "sdist")
        records[name] = download(source["url"], tree / "python" / source["filename"], source["digests"]["sha256"])
    (tree / "UPSTREAM.json").write_text(json.dumps(records, indent=2) + "\n")
    (tree / "README.txt").write_text(
        "Dependency sources for the accompanying Follow Executor image.\n"
        "INVENTORY.json maps every installed Debian binary to its exact source version.\n"
        "debian/ contains apt-verified .dsc files, upstream sources and Debian patches.\n"
        "Use dpkg-source -x PACKAGE.dsc to extract a Debian source package.\n"
        "ibkr/ contains the unchanged, checksum-pinned official API source archive.\n"
        "python/ contains CPython and installed Python dependency source distributions.\n"
        "UPSTREAM.json records download locations and checksums.\n"
        "notices/ retains upstream copyright and license files.\n"
        "The application source archive contains its Dockerfile, lock files and build scripts.\n"
        "Third-party components retain their own licenses. No Gateway image is redistributed here.\n")
    hashes = {p.relative_to(tree).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sorted(tree.rglob("*")) if p.is_file() and p.name != "SHA256SUMS"}
    (tree / "SHA256SUMS").write_text("".join(f"{digest}  {name}\n" for name, digest in hashes.items()))
    archive = args.output / "third-party-source.tar.gz"
    with (
        archive.open("wb") as raw,
        gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as compressed,
        tarfile.open(fileobj=compressed, mode="w") as tar,
    ):
        for path in sorted(tree.rglob("*")):
            if path.is_file():
                info = tar.gettarinfo(str(path), arcname="third-party-source/"+path.relative_to(tree).as_posix())
                info.uid = info.gid = info.mtime = 0
                info.uname = info.gname = ""
                info.mode = 0o644
                with path.open("rb") as source:
                    tar.addfile(info, source)
    manifest = {"archive": archive.name, "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
                "inventory": inventory, "files": hashes}
    (args.output / "SOURCES.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(archive)


if __name__ == "__main__":
    main()
