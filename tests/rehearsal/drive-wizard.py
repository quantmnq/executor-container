#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Follow Executor contributors
"""Drive only the unauthenticated wizard on a disposable localhost SSH guest.

Uses dummy account/token data, never enters IBKR credentials, never starts Gateway
or trading. Requires a separate VM: do not point this at a forwarded customer host.
"""
from __future__ import annotations

import argparse
import errno
import os
import pty
import select
import shlex
import subprocess
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--identity", type=Path, required=True)
    parser.add_argument("--known-hosts", type=Path, required=True)
    parser.add_argument("--port", type=int, default=22292)
    parser.add_argument("--container", help="run SSH inside the QEMU helper to avoid nested Docker subnet conflicts")
    parser.add_argument("--release", required=True)
    parser.add_argument("--phase", choices=("decline", "docker", "configure", "resume"), required=True)
    parser.add_argument("--log", type=Path, required=True)
    args = parser.parse_args()
    if args.phase in ("docker", "decline"):
        prompts = [("using sudo? [y/N]:", "y\n" if args.phase == "docker" else "n\n")]
    elif args.phase == "configure":
        prompts = [("Account mode [paper]:", "paper\n"),
                   ("IBKR account ID (for example DU1234567):", "DU1234567\n"),
                   ("Instrument [MNQ]:", "MNQ\n"), ("Number of contracts (1–10) [1]:", "1\n"),
                   ("Personal relay token (hidden):", "disposable-rehearsal-token\n"),
                   ("4/5  Gateway login", "\x03")]
    else:
        prompts = [("4/5  Gateway login", "\x03")]
    command = ("test \"$(hostname)\" = follow-rehearsal && "
               f"cd {shlex.quote(args.release)} && ./follow-stack setup --no-vnc")
    ssh = ["ssh", "-tt", "-i", str(args.identity), "-p", str(args.port),
           "-o", "StrictHostKeyChecking=yes", "-o", f"UserKnownHostsFile={args.known_hosts}",
           "-o", "ConnectTimeout=30", "ubuntu@127.0.0.1", command]
    if args.container:
        ssh = ["docker", "exec", "-it", args.container, "ssh", "-tt", "-i", f"/vm/{args.identity.name}", "-p", "2222",
               "-o", "StrictHostKeyChecking=yes", "-o", f"HostKeyAlias=[127.0.0.1]:{args.port}",
               "-o", f"UserKnownHostsFile=/vm/{args.known_hosts.name}", "-o", "ConnectTimeout=60",
               "ubuntu@127.0.0.1", command]
    master, slave = pty.openpty()
    process = subprocess.Popen(ssh, stdin=slave, stdout=slave, stderr=slave, start_new_session=True)
    os.close(slave)
    position, text = 0, b""
    deadline = time.monotonic() + 2400
    args.log.parent.mkdir(parents=True, exist_ok=True)
    try:
        with args.log.open("wb") as transcript:
            os.chmod(args.log, 0o600)
            while time.monotonic() < deadline:
                readable, _, _ = select.select([master], [], [], 1)
                if readable:
                    try:
                        chunk = os.read(master, 65536)
                    except OSError as exc:
                        if exc.errno == errno.EIO:
                            break
                        raise
                    if not chunk:
                        break
                    transcript.write(chunk)
                    transcript.flush()
                    text += chunk
                    if position < len(prompts) and prompts[position][0].encode() in text:
                        os.write(master, prompts[position][1].encode())
                        print(f"Answered fixture checkpoint {position + 1}/{len(prompts)} ({args.phase})", flush=True)
                        position += 1
                        text = b""
                elif process.poll() is not None:
                    break
            else:
                raise TimeoutError("Disposable guest wizard timed out; see private fixture transcript")
        code = process.wait(timeout=30)
        expected = (3,) if args.phase in ("docker", "decline") else (130,)
        if code not in expected or position != len(prompts):
            raise RuntimeError(f"Guest wizard exit={code}; prompts={position}/{len(prompts)}; see {args.log}")
        print(f"PASS {args.phase}: exit {code}; no IBKR credentials entered or trading started.")
    finally:
        if process.poll() is None:
            process.terminate()
        os.close(master)


if __name__ == "__main__":
    main()
