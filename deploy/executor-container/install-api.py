# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Follow Executor contributors
"""Build the checksum-verified official IBKR API; never use PyPI's ibapi."""

import hashlib
import io
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

URL = "https://interactivebrokers.github.io/downloads/twsapi_macunix.1050.02.zip"
SHA256 = "673129e5cba58c4d77bc40647265f84ea42f605eccf88fa4c1221d62d12454f3"

with urllib.request.urlopen(URL, timeout=120) as response:
    data = response.read()
if hashlib.sha256(data).hexdigest() != SHA256:
    raise RuntimeError("Official IBKR API archive checksum mismatch")
with zipfile.ZipFile(io.BytesIO(data)) as archive:
    archive.extractall("/build/api")
notices = Path("/build/api-notices")
notices.mkdir(parents=True, exist_ok=True)
for name in ("LICENSE", "NOTICE"):
    shutil.copyfile(Path("/build/api/IBJts") / name, notices / name)
shutil.copytree("/build/api/IBJts/THIRD_PARTY_LICENSES", notices / "THIRD_PARTY_LICENSES",
                dirs_exist_ok=True)
Path("/wheels").mkdir(exist_ok=True)
subprocess.run([
    sys.executable, "-m", "pip", "wheel", "--no-deps", "--no-build-isolation",
    "--wheel-dir", "/wheels", "/build/api/IBJts/source/pythonclient",
], check=True)
