# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Follow Executor contributors
from __future__ import annotations

import io
import json
import os
import runpy
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IMAGE_ID = "sha256:" + "a" * 64


class ContainerPackagingTests(unittest.TestCase):
    def test_context_cannot_include_checkout_state_or_application_source(self):
        builder = runpy.run_path(str(ROOT / "scripts/build-executor-container.py"))
        version, files = builder["context_files"]()
        wheel = f"follow_executor-{version}-cp312-none-any.whl"
        self.assertEqual(set(files), {wheel, "Dockerfile", "requirements.lock",
                                     "build-requirements.lock", "install-api.py",
                                     "LICENSE", "NOTICE", "THIRD_PARTY_NOTICES.md"})
        with zipfile.ZipFile(io.BytesIO(files[wheel])) as archive:
            self.assertFalse(any(name.endswith(".py") for name in archive.namelist()))
        # A version bump must not silently leave the operator launcher on an old image.
        self.assertIn(f"follow-executor:{version}", (ROOT / "follow-container").read_text())


class ContainerLauncherTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.env = dict(os.environ, PATH=f"{self.bin}:{os.environ['PATH']}",
                        XDG_CONFIG_HOME=str(self.root / "config space"),
                        XDG_STATE_HOME=str(self.root / "state space"),
                        TEST_CALLS=str(self.root / "calls.jsonl"), TEST_IMAGE=IMAGE_ID)
        # Only Docker/systemd are mocked. The launcher's quoting and argument vectors
        # execute in Bash, so broken quoting cannot hide behind string assertions.
        tool = """#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
name = Path(sys.argv[0]).name
with open(os.environ['TEST_CALLS'], 'a') as out:
    out.write(json.dumps([name, *sys.argv[1:]]) + '\\n')
if name == 'docker':
    if sys.argv[1:3] == ['image', 'inspect']:
        print(os.environ['TEST_IMAGE'])
    elif sys.argv[1] == 'run':
        raise SystemExit(int(os.environ.get('TEST_CHECK_EXIT', '0')))
elif name == 'systemctl' and any(a in sys.argv for a in ['is-active', 'is-enabled']):
    raise SystemExit(1)
"""
        for name in ("docker", "systemctl"):
            path = self.bin / name
            path.write_text(tool)
            path.chmod(0o755)

    def run_launcher(self, *args, **env):
        result = subprocess.run([str(ROOT / "follow-container"), *args],
                                env=self.env | env, text=True, capture_output=True,
                                check=False)
        return result

    def calls(self):
        path = self.root / "calls.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines()]

    def install(self):
        result = self.run_launcher("install")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_install_pins_image_and_creates_stopped_service_with_graceful_stop(self):
        self.install()
        calls = self.calls()
        self.assertFalse(any("enable" in call or "run" in call for call in calls))
        unit = next((self.root / "config space/systemd/user").glob("*.service")).read_text()
        self.assertIn(IMAGE_ID, unit)
        self.assertIn('"--network" "host"', unit)
        self.assertIn('"--read-only"', unit)
        self.assertIn('"--user"', unit)
        self.assertIn('"--restart" "no"', unit)
        self.assertIn('"stop" "--time" "45"', unit)
        self.assertIn("RestartPreventExitStatus=2", unit)
        self.assertIn("TimeoutStopSec=60", unit)
        if shutil.which("systemd-analyze"):
            path = next((self.root / "config space/systemd/user").glob("*.service"))
            result = subprocess.run(["systemd-analyze", "--user", "verify", str(path)],
                                    text=True, capture_output=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_failed_check_cannot_enable_or_start_trading(self):
        self.install()
        result = self.run_launcher("start", TEST_CHECK_EXIT="1", FOLLOW_CHECK_QUOTES="1")
        self.assertEqual(result.returncode, 1)
        calls = self.calls()
        self.assertTrue(any(call[0:2] == ["docker", "run"] and "check" in call and "--quotes" in call for call in calls))
        self.assertFalse(any("enable" in call for call in calls))

    def test_start_checks_pinned_image_before_enabling_service(self):
        self.install()
        result = self.run_launcher("start", FOLLOW_EXECUTOR_IMAGE="different:tag")
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.calls()
        check = next(i for i, call in enumerate(calls) if "check" in call)
        enable = next(i for i, call in enumerate(calls) if "enable" in call)
        self.assertLess(check, enable)
        self.assertIn(IMAGE_ID, calls[check])
        self.assertNotIn("different:tag", calls[check])
        self.assertIn(f"type=bind,src={self.root}/config space/follow-executor,"
                      f"dst={self.root}/config space/follow-executor,bind-recursive=disabled", calls[check])

    def test_all_executor_commands_and_service_obscure_credentials_and_backups(self):
        self.install()
        protected = (self.root / "config space/follow-executor/gateway",
                     self.root / "state space/follow-executor/maintenance")
        for path in protected:
            self.assertEqual(path.stat().st_mode & 0o777, 0o700)
        for action in ("configure", "check", "settings", "discord", "status", "watch", "resume",
                       "maintenance-check"):
            with self.subTest(action=action):
                result = self.run_launcher(action, FOLLOW_EXECUTOR_PROBE_IMAGE=IMAGE_ID)
                self.assertEqual(result.returncode, 0, result.stderr)
                args = self.calls()[-1]
                for path in protected:
                    self.assertIn(f"{path}:ro,noexec,nosuid,nodev,size=64k,mode=0000", args)
        unit = next((self.root / "config space/systemd/user").glob("*.service")).read_text()
        for path in protected:
            self.assertIn(f'"--tmpfs" "{path}:ro,noexec,nosuid,nodev,size=64k,mode=0000"', unit)

    def test_start_refuses_service_installed_before_credential_isolation(self):
        self.install()
        path = next((self.root / "config space/systemd/user").glob("*.service"))
        text = path.read_text()
        mask = (f'"--tmpfs" "{self.root}/config space/follow-executor/gateway:'
                'ro,noexec,nosuid,nodev,size=64k,mode=0000" ')
        self.assertIn(mask, text)
        path.write_text(text.replace(mask, ""))
        result = self.run_launcher("start")
        self.assertEqual(result.returncode, 2)
        self.assertIn("reinstall", result.stderr)
        self.assertFalse(any("enable" in call or "run" in call for call in self.calls()))

    def test_rejects_path_aliases_that_could_expose_the_protected_subtrees(self):
        config_base = self.root / "config space"
        config = config_base / "follow-executor"
        config.mkdir(parents=True)
        outside = self.root / "private-fixture"
        outside.mkdir()
        (config / "gateway").symlink_to(outside, target_is_directory=True)
        result = self.run_launcher("install")
        self.assertEqual(result.returncode, 2)
        self.assertIn("symlinks", result.stderr)
        (config / "gateway").unlink()
        for state_base in (str(config_base), str(config / "nested")):
            with self.subTest(state_base=state_base):
                result = self.run_launcher("install", XDG_STATE_HOME=state_base)
                self.assertEqual(result.returncode, 2)
                self.assertIn("non-overlapping", result.stderr)
        result = self.run_launcher("install", XDG_CONFIG_HOME=str(self.root / "bad:path"))
        self.assertEqual(result.returncode, 2)
        self.assertIn("colon", result.stderr)
        (self.root / "base-alias").symlink_to(self.root / "bad:path", target_is_directory=True)
        result = self.run_launcher("install", XDG_CONFIG_HOME=str(self.root / "base-alias"))
        self.assertEqual(result.returncode, 2)
        self.assertIn("Resolved XDG", result.stderr)
        self.assertFalse((self.root / "calls.jsonl").exists())

    def test_stop_disables_without_invoking_broker_commands(self):
        self.install()
        result = self.run_launcher("stop")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("disable", self.calls()[-1])
        self.assertFalse(any(call[0:2] == ["docker", "run"] for call in self.calls()))


if __name__ == "__main__":
    unittest.main()
