# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Follow Executor contributors
from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
import os
import runpy
import subprocess
import sys
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class BytecodeReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.directory.cleanup)
        cls.output = Path(cls.directory.name)
        cls.builder = runpy.run_path(str(ROOT / "scripts/build-bytecode.py"))
        cls.archive = cls.builder["build"](cls.output)

    def test_archive_is_reproducible_and_contains_only_customer_files(self):
        before = self.archive.read_bytes()
        self.builder["build"](self.output)
        self.assertEqual(before, self.archive.read_bytes())
        with tarfile.open(self.archive) as archive:
            files = {member.name.split("/", 1)[1]: archive.extractfile(member).read()
                     for member in archive.getmembers()}
        expected = {"README.md", "RELEASE.json", "SHA256SUMS", "install.sh", "follow", "follow-container", "follow-stack",
                    "LICENSE", "NOTICE", "THIRD_PARTY_NOTICES.md",
                    "scripts/stack-bootstrap.py",
                    "START_HERE.md", "START_HERE.zh-CN.md", "AGENTS.md", "CLAUDE.md",
                    "scripts/install-ibapi.sh", "scripts/install-ibc.sh", "scripts/install-docker.sh",
                    "scripts/gateway-desktop.sh", "licenses/ib-gateway-docker-MIT.txt"}
        expected.update(f"docs/{name}{suffix}" for name in self.builder["CUSTOMER_DOCS"]
                        for suffix in (".md", ".zh-CN.md"))
        screenshots = {
            "docs/images/ib-gateway-configure-menu.png",
            "docs/images/ib-gateway-api-settings.png",
            "docs/images/discord-bot-setup-link.png",
        }
        expected.update(screenshots)
        for name in screenshots:
            self.assertTrue(files[name].startswith(b"\x89PNG\r\n\x1a\n"), name)
            for guide in ("docs/SETUP.md", "docs/SETUP.zh-CN.md"):
                self.assertIn(f"]({name.removeprefix('docs/')})", files[guide].decode())
        for guide in ("docs/DISCORD.md", "docs/DISCORD.zh-CN.md"):
            self.assertIn(
                "](images/discord-bot-setup-link.png)", files[guide].decode(),
            )
        release = json.loads(files["RELEASE.json"])
        expected.add(release["wheel"])
        expected.add(release["source"]["archive"])
        expected.update(p.relative_to(ROOT).as_posix() for p in (ROOT / "licenses").rglob("*") if p.is_file())
        self.assertEqual(set(files), expected)
        self.assertEqual(hashlib.sha256(files[release["wheel"]]).hexdigest(),
                         release["wheel_sha256"])
        checksums = dict(line.split("  ", 1)[::-1]
                         for line in files["SHA256SUMS"].decode().splitlines())
        self.assertEqual(set(checksums), set(files) - {"SHA256SUMS"})
        for name, digest in checksums.items():
            self.assertEqual(hashlib.sha256(files[name]).hexdigest(), digest)

    def test_corresponding_source_rebuilds_identical_wheel_without_checkout(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with tarfile.open(self.archive) as kit:
                kit.extractall(root / "kit", filter="data")
            release_root = next((root / "kit").iterdir())
            release = json.loads((release_root / "RELEASE.json").read_text())
            source_path = release_root / release["source"]["archive"]
            self.assertEqual(hashlib.sha256(source_path.read_bytes()).hexdigest(), release["source"]["sha256"])
            with tarfile.open(source_path) as source:
                source.extractall(root / "source", filter="data")
            checkout = next((root / "source").iterdir())
            manifest = json.loads((checkout / "SOURCE.json").read_text())
            self.assertEqual(manifest["license"], "GPL-3.0-or-later")
            self.assertNotIn("docs/RELEASE_HANDOFF.md", manifest["files"])
            self.assertFalse((checkout / ".git").exists())
            for name, digest in manifest["files"].items():
                self.assertEqual(hashlib.sha256((checkout / name).read_bytes()).hexdigest(), digest)
            subprocess.run([sys.executable, str(checkout / "scripts/build-bytecode.py"),
                            "--output", str(root / "rebuilt")], check=True, capture_output=True)
            wheel = next((root / "rebuilt").glob("*.whl"))
            self.assertEqual(hashlib.sha256(wheel.read_bytes()).hexdigest(), release["wheel_sha256"])
            with zipfile.ZipFile(wheel) as archive:
                metadata = archive.read(next(n for n in archive.namelist() if n.endswith('/METADATA')))
                self.assertIn(b"License-Expression: GPL-3.0-or-later", metadata)
                self.assertTrue(any(n.endswith('/licenses/LICENSE') for n in archive.namelist()))

    def test_source_export_rejects_symlink_to_private_file(self):
        source_builder = runpy.run_path(str(ROOT / "scripts/build-source.py"))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "deploy").mkdir()
            (root / "src/follow_executor").mkdir(parents=True)
            (root / "deploy/public-files.txt").write_text("public.py\n")
            (root / "private.txt").write_text("synthetic secret")
            (root / "public.py").symlink_to(root / "private.txt")
            source_builder["public_files"].__globals__["ROOT"] = root
            with self.assertRaisesRegex(ValueError, "Invalid public export"):
                source_builder["public_files"]()

    def test_wheel_has_every_module_no_source_and_valid_records(self):
        wheel = next(self.output.glob("*.whl"))
        with zipfile.ZipFile(wheel) as archive:
            names = archive.namelist()
            self.assertFalse(any(name.endswith(".py") for name in names))
            expected = {source.relative_to(ROOT / "src").with_suffix(".pyc").as_posix()
                        for source in (ROOT / "src/follow_executor").rglob("*.py")}
            self.assertEqual({name for name in names if name.endswith(".pyc")}, expected)
            record = next(name for name in names if name.endswith("/RECORD"))
            for name, digest, size in csv.reader(io.StringIO(archive.read(record).decode())):
                if name == record:
                    continue
                data = archive.read(name)
                actual = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=")
                self.assertEqual(digest, f"sha256={actual.decode()}")
                self.assertEqual(int(size), len(data))

    def test_all_modules_and_cli_run_without_source(self):
        with tempfile.TemporaryDirectory() as installed:
            with zipfile.ZipFile(next(self.output.glob("*.whl"))) as archive:
                archive.extractall(installed)
            code = """
import importlib
import importlib.machinery
import pkgutil
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import follow_executor
package = Path(follow_executor.__file__).parent
assert package.parent == Path(sys.argv[1])
assert not list(package.rglob('*.py'))
for name in ['follow_executor', *(m.name for m in pkgutil.walk_packages(
        [str(package)], 'follow_executor.'))]:
    module = importlib.import_module(name)
    assert isinstance(module.__loader__, importlib.machinery.SourcelessFileLoader), name
from follow_executor.cli import main
sys.argv = ['follow-executor', '--help']
main()
"""
            result = subprocess.run([sys.executable, "-I", "-c", code, installed],
                                    text=True, capture_output=True, cwd=installed, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("discord", result.stdout)

    def test_wizard_bootstrap_needs_no_host_dependencies_and_rejects_tampering(self):
        with tempfile.TemporaryDirectory() as temporary:
            with tarfile.open(self.archive) as archive:
                archive.extractall(temporary, filter="data")
            release = next(Path(temporary).iterdir())
            # -S removes site-packages, including cryptography and ibapi. The
            # controller must import directly from the bytecode wheel with stdlib.
            command = [sys.executable, "-I", "-S", str(release / "scripts/stack-bootstrap.py"), "--help"]
            result = subprocess.run(command, text=True, capture_output=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("setup", result.stdout)
            self.assertIn("doctor", result.stdout)
            with (release / "follow-container").open("a") as handle:
                handle.write("\n# corrupted\n")
            result = subprocess.run(command, text=True, capture_output=True, check=False)
            self.assertEqual(result.returncode, 2)
            self.assertIn("verification failed", result.stderr)

    def test_combined_bundle_requires_matching_image_and_covers_archive(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            image_archive = root / "executor.tar.gz"
            image_archive.write_bytes(b"test image archive")
            wheel = next(self.output.glob("*.whl"))
            metadata = {"id": "sha256:" + "a" * 64, "platform": "linux/arm64",
                        "wheel_sha256": hashlib.sha256(wheel.read_bytes()).hexdigest()}
            path = self.builder["build"](root / "output", executor_image=metadata, image_archive=image_archive)
            with tarfile.open(path) as archive:
                archive.extractall(root / "extracted", filter="data")
            release = next((root / "extracted").iterdir())
            saved = json.loads((release / "RELEASE.json").read_text())["executor_image"]
            self.assertEqual((release / saved["archive"]).read_bytes(), image_archive.read_bytes())
            self.assertEqual(saved["archive_sha256"], hashlib.sha256(image_archive.read_bytes()).hexdigest())
            self.assertTrue(os.access(release / "follow-stack", os.X_OK))
            with self.assertRaisesRegex(ValueError, "exact release wheel"):
                self.builder["build"](root / "wrong", executor_image=metadata | {"wheel_sha256": "wrong"},
                                      image_archive=image_archive)
