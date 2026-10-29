#!/usr/bin/env python3.12
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Follow Executor contributors
"""Build the customer kit from an explicit allowlist; never archive the checkout."""

from __future__ import annotations

import argparse
import base64
import csv
import gzip
import hashlib
import importlib.util
import io
import json
import re
import runpy
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TAG = "cp312-none-any"
CUSTOMER_DOCS = (
    "IBKR_ACCOUNT_SETUP",
    "AGENT_SETUP", "SETUP", "SETUP_NATIVE", "IBC", "GATEWAY_DOCKER", "EXECUTOR_DOCKER", "CONTAINER_SETUP", "DISCORD", "EXECUTOR", "OCI_ARM", "OPERATIONS", "SIGNAL_V1", "RELEASE_NOTES", "SOURCE", "RELEASING",
    "UPGRADE",
)
CUSTOMER_IMAGES = (
    "ib-gateway-configure-menu.png", "ib-gateway-api-settings.png",
    "discord-bot-setup-link.png",
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def wheel_bytes(project: dict) -> bytes:
    """Legacy module.pyc paths are necessary for imports without .py sources."""
    files = {}
    with tempfile.TemporaryDirectory(prefix="follow-bytecode-") as directory:
        # CPython's marshal reference flags can depend on constants retained by
        # imported application modules. Compile in a fresh interpreter so a test
        # runner or an imported executor cannot change the resulting wheel.
        compiler = """
import py_compile
import sys
from pathlib import Path
source_root, output = map(Path, sys.argv[1:])
for source in sorted((source_root / "follow_executor").rglob("*.py")):
    relative = source.relative_to(source_root)
    py_compile.compile(
        str(source), cfile=str(output / relative.with_suffix(".pyc")),
        dfile=relative.as_posix(), doraise=True, optimize=0,
        invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH,
    )
"""
        subprocess.run([sys.executable, "-I", "-S", "-c", compiler,
                        str(ROOT / "src"), directory], check=True)
        for compiled in sorted(Path(directory).rglob("*.pyc")):
            files[compiled.relative_to(directory).as_posix()] = compiled.read_bytes()
    if "follow_executor/__init__.pyc" not in files:
        raise RuntimeError("Missing package initializer")

    info = f"follow_executor-{project['version']}.dist-info"
    metadata = [
        "Metadata-Version: 2.4", "Name: follow-executor",
        f"Version: {project['version']}", f"Summary: {project['description']}",
        "License-Expression: GPL-3.0-or-later",
        "License-File: LICENSE", "License-File: NOTICE",
        "Requires-Python: >=3.12,<3.13",
        *(f"Requires-Dist: {item}" for item in project["dependencies"]),
    ]
    files[f"{info}/METADATA"] = ("\n".join(metadata) + "\n\n").encode()
    for name in ("LICENSE", "NOTICE"):
        files[f"{info}/licenses/{name}"] = (ROOT / name).read_bytes()
    files[f"{info}/WHEEL"] = (
        "Wheel-Version: 1.0\nGenerator: follow-executor-bytecode\n"
        f"Root-Is-Purelib: true\nTag: {TAG}\n"
    ).encode()
    entries = ["[console_scripts]", *(
        f"{name} = {target}" for name, target in project["scripts"].items()
    )]
    files[f"{info}/entry_points.txt"] = ("\n".join(entries) + "\n").encode()
    record = io.StringIO(newline="")
    writer = csv.writer(record, lineterminator="\n")
    for name, content in sorted(files.items()):
        digest = base64.urlsafe_b64encode(hashlib.sha256(content).digest()).rstrip(b"=")
        writer.writerow((name, f"sha256={digest.decode()}", len(content)))
    writer.writerow((f"{info}/RECORD", "", ""))
    files[f"{info}/RECORD"] = record.getvalue().encode()
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as wheel:
        for name, content in sorted(files.items()):
            entry = zipfile.ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o100644 << 16
            wheel.writestr(entry, content)
    return archive.getvalue()


def build(output: Path, *, executor_image: dict | None = None, image_archive: Path | None = None,
          third_party_source: dict | None = None) -> Path:
    if sys.implementation.name != "cpython" or sys.version_info[:2] != (3, 12):
        raise RuntimeError("Build with CPython 3.12; bytecode is Python-version specific")
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    version = project["version"]
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("Use a three-part release version, for example 0.1.0")
    name = "follow-stack" if executor_image else "follow-executor"
    release = f"{name}-{version}-ubuntu24.04-arm64-cp312"
    wheel_name = f"follow_executor-{version}-{TAG}.whl"
    files = {f"wheels/{wheel_name}": wheel_bytes(project)}
    source_name = f"follow-executor-{version}-source.tar.gz"
    source_blob = runpy.run_path(str(ROOT / "scripts/build-source.py"))["source_bytes"](project)
    files[f"sources/{source_name}"] = source_blob
    copies = {
        "LICENSE": "LICENSE",
        "NOTICE": "NOTICE",
        "THIRD_PARTY_NOTICES.md": "THIRD_PARTY_NOTICES.md",
        "START_HERE.md": "START_HERE.md",
        "START_HERE.zh-CN.md": "START_HERE.zh-CN.md",
        "AGENTS.md": "deploy/customer/AGENTS.md",
        "CLAUDE.md": "deploy/customer/CLAUDE.md",
        "install.sh": "deploy/install-bytecode.sh",
        "follow": "follow",
        "follow-container": "follow-container",
        "follow-stack": "follow-stack",
        "scripts/stack-bootstrap.py": "scripts/stack-bootstrap.py",
        "scripts/install-ibapi.sh": "scripts/install-ibapi.sh",
        "scripts/install-ibc.sh": "scripts/install-ibc.sh",
        "scripts/install-docker.sh": "scripts/install-docker.sh",
        "scripts/gateway-desktop.sh": "scripts/gateway-desktop.sh",
        "licenses/ib-gateway-docker-MIT.txt": "licenses/ib-gateway-docker-MIT.txt",
    }
    for name in CUSTOMER_DOCS:
        for suffix in (".md", ".zh-CN.md"):
            copies[f"docs/{name}{suffix}"] = f"docs/{name}{suffix}"
    for name in CUSTOMER_IMAGES:
        copies[f"docs/images/{name}"] = f"docs/images/{name}"
    for path in sorted((ROOT / "licenses").rglob("*")):
        if path.is_file():
            copies[path.relative_to(ROOT).as_posix()] = path.relative_to(ROOT).as_posix()
    for destination, source in copies.items():
        files[destination] = (ROOT / source).read_bytes()
    files["README.md"] = (
        f"# Auto Quant Follow Executor {version}\n\n"
        "Customer installation kit for Ubuntu 24.04 ARM64 and CPython 3.12.\n\n"
        "- [Start here with Codex or Claude Code](START_HERE.md)\n"
        "- [从这里开始：用 Codex 或 Claude Code 安装](START_HERE.zh-CN.md)\n"
        "- [Complete setup steps in English](docs/SETUP_NATIVE.md)\n"
        "- [完整中文安装指南](docs/SETUP_NATIVE.zh-CN.md)\n\n"
        "Open this folder in Codex or Claude Code and paste the START_HERE prompt.\n"
        "The AI tool needs access to the files and VM; personal login/phone steps still need you.\n"
        "Install on Ubuntu with `./install.sh` as your Ubuntu login user.\n"
        "Installation does not start trading. Keep this directory at its installed path.\n"
    ).encode()
    metadata = {
        "name": project["name"], "version": version,
        "os": "ubuntu", "os_version": "24.04", "architecture": "aarch64",
        "python": "cpython-3.12", "bytecode_magic": importlib.util.MAGIC_NUMBER.hex(),
        "build_python_version": sys.version.split()[0],
        "wheel": f"wheels/{wheel_name}", "wheel_sha256": sha256(files[f"wheels/{wheel_name}"]),
        "license": "GPL-3.0-or-later",
        "source": {"archive": f"sources/{source_name}", "sha256": sha256(source_blob)},
    }
    if executor_image:
        if image_archive is None or executor_image["wheel_sha256"] != metadata["wheel_sha256"]:
            raise ValueError("Executor image must contain this exact release wheel")
        files["images/executor.tar.gz"] = image_archive.read_bytes()
        metadata["executor_image"] = {**executor_image, "archive": "images/executor.tar.gz",
                                      "archive_sha256": sha256(files["images/executor.tar.gz"])}
        if third_party_source is not None:
            metadata["third_party_source"] = third_party_source
        files["README.md"] = (
            f"# Auto Quant container setup {version}\n\n"
            "Combined Gateway and executor kit for Ubuntu 24.04 ARM64.\n\n"
            "Open this extracted folder in Codex or Claude Code and paste the START_HERE\n"
            "prompt. The assistant guides account preparation, OCI and installation from scratch.\n\n"
            "- [Start here with Codex or Claude Code](START_HERE.md)\n"
            "- [从这里开始：用 Codex 或 Claude Code 安装](START_HERE.zh-CN.md)\n"
            "- [Beginner setup in English](docs/SETUP.md)\n"
            "- [零基础中文安装指南](docs/SETUP.zh-CN.md)\n\n"
            "New OCI setup: US West (San Jose), select the offline-authenticator checkbox\n"
            "before MFA enrollment, add payment and upgrade to Pay As You Go before VCN,\n"
            "then create Ubuntu 24.04 ARM64 with 2 OCPUs / 12 GB RAM.\n"
            "Prepare the IBKR additional account and secondary username first; keep separate\n"
            "usernames for Gateway and phone trading, and verify the actual paper login.\n"
            "See [IBKR preparation](docs/IBKR_ACCOUNT_SETUP.md) / "
            "[IBKR 账户准备](docs/IBKR_ACCOUNT_SETUP.zh-CN.md).\n\n"
            "Request Futures with accurate experience; complete both gear-icon Market Data API\n"
            "Acknowledgement and Subscriber Status forms. Eligible Non-Professional users select\n"
            "CME Real-Time (L1), listed at $1.55/month, and confirm IBKR's current recurring fee.\n\n"
            "Verify the archive checksum, extract it into a permanent\n"
            "directory on Ubuntu, and run `./follow-stack setup` in your own terminal.\n"
            "The wizard resumes saved steps and never starts trading. It asks for a leverage\n"
            "fraction (above 0, at most 1) of the leader's 6x band and previews the\n"
            "NQ + MNQ split. After readiness checks, review your mode and size and explicitly\n"
            "run `./follow-stack start`.\n\n"
            "Updating an existing 0.2.0 installation? Follow the upgrade guide while flat:\n"
            "- [Upgrade from 0.2.0](docs/UPGRADE.md)\n"
            "- [从 0.2.0 升级](docs/UPGRADE.zh-CN.md)\n\n"
            "- [Container maintenance and recovery reference](docs/CONTAINER_SETUP.md)\n"
            "- [中文容器维护与恢复参考](docs/CONTAINER_SETUP.zh-CN.md)\n\n"
            "- [Release notes and validation scope](docs/RELEASE_NOTES.md)\n"
            "- [版本说明及验证范围](docs/RELEASE_NOTES.zh-CN.md)\n\n"
            "Download sources: Docker Engine comes from Docker's official Ubuntu repository;\n"
            "Gateway comes from the pinned upstream GitHub container registry image;\n"
            "the executor image is included in this archive. Discord may carry the Auto Quant\n"
            "archive or its download link; it is not the Docker Engine download source.\n\n"
            "IBKR credentials stay on your VM. You handle phone approval and login notices.\n"
            "Keep this directory in place: it runs the Gateway supervisor.\n"
        ).encode()
    files["README.md"] += (
        "\nGPL-3.0-or-later: matching application source is included under `sources/`.\n"
        "See [source, licenses and rebuilding](docs/SOURCE.md) or "
        "[源码、许可与构建](docs/SOURCE.zh-CN.md).\n"
        "For container dependencies, download the matching dependency source archive "
        "from the same release page; its filename and hash are in RELEASE.json.\n"
    ).encode()
    files["RELEASE.json"] = (json.dumps(metadata, indent=2) + "\n").encode()
    files["SHA256SUMS"] = "".join(
        f"{sha256(data)}  {name}\n" for name, data in sorted(files.items())
    ).encode()

    output.mkdir(parents=True, exist_ok=True)
    archive_path = output / f"{release}.tar.gz"
    # Fixed archive metadata makes repeated builds of identical inputs identical.
    with (
        archive_path.open("wb") as raw,
        gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed,
        tarfile.open(fileobj=compressed, mode="w") as archive,
    ):
        for name, content in sorted(files.items()):
            entry = tarfile.TarInfo(f"{release}/{name}")
            entry.size = len(content)
            entry.mode = 0o755 if name in ("follow", "follow-container", "follow-stack") or name.endswith(".sh") else 0o644
            archive.addfile(entry, io.BytesIO(content))
    (output / wheel_name).write_bytes(files[f"wheels/{wheel_name}"])
    (output / source_name).write_bytes(source_blob)
    archive_path.with_suffix(archive_path.suffix + ".sha256").write_text(
        f"{sha256(archive_path.read_bytes())}  {archive_path.name}\n"
    )
    return archive_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist/bytecode")
    print(build(parser.parse_args().output.resolve()))
