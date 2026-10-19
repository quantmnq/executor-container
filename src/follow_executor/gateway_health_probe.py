# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Follow Executor contributors
"""Isolated API handshake probe. No trading journal, market data or order access."""

from __future__ import annotations

import argparse
import json
import logging
import signal
import threading
import time
from pathlib import Path

from .config import load_config

CLIENT_ID = 9701
TIMEOUT = 15


def client():
    # Lazy import: the host wizard needs only Python's standard library. The
    # combined kit runs this module inside its pinned executor image.
    from ibapi.client import PROTOBUF_MSG_ID, EClient
    from ibapi.message import OUT
    from ibapi.wrapper import EWrapper

    allowed = {int(OUT.START_API), int(OUT.REQ_MANAGED_ACCTS)}

    class Handshake(EWrapper, EClient):
        def __init__(self):
            EWrapper.__init__(self)
            EClient.__init__(self, self)
            self.ready = threading.Event()
            self.managed = threading.Event()
            self.accounts = set()
            self.conflict = False

        def sendMsg(self, msgId, msg):
            if int(msgId) not in allowed:
                raise PermissionError("Gateway health probe permits only API handshake messages")
            return super().sendMsg(msgId, msg)

        def sendMsgProtoBuf(self, msgId, msg):
            if int(msgId) - PROTOBUF_MSG_ID not in allowed:
                raise PermissionError("Gateway health probe permits only API handshake messages")
            return super().sendMsgProtoBuf(msgId, msg)

        def nextValidId(self, orderId):
            self.ready.set()

        def managedAccounts(self, accountsList):
            self.accounts = {value.strip() for value in accountsList.split(",") if value.strip()}
            self.managed.set()

        def error(self, reqId, errorTime, errorCode, errorString, advancedOrderRejectJson=""):
            if errorCode == 326:
                self.conflict = True
                self.ready.set()
                self.managed.set()

        def nextValidIdProtoBuf(self, message):
            self.nextValidId(message.orderId)

        def managedAccountsProtoBuf(self, message):
            self.managedAccounts(message.accountsList)

        def errorProtoBuf(self, message):
            self.error(message.id, message.errorTime, message.errorCode, "")

    return Handshake()


def probe(settings, *, factory=client, timeout=TIMEOUT):
    if settings.host != "127.0.0.1" or settings.client_id == CLIENT_ID:
        return "monitor_error"
    app = factory()
    deadline = time.monotonic() + timeout
    thread = None
    try:
        app.connect(settings.host, settings.port, CLIENT_ID)
        thread = threading.Thread(target=app.run, daemon=True)
        thread.start()
        if not app.ready.wait(max(0, deadline - time.monotonic())):
            return "unavailable"
        if app.conflict:
            return "monitor_error"
        app.reqManagedAccts()
        if not app.managed.wait(max(0, deadline - time.monotonic())) or not app.isConnected():
            return "unavailable"
        if app.conflict:
            return "monitor_error"
        return "healthy" if settings.account in app.accounts else "account_mismatch"
    except (OSError, TimeoutError, ConnectionError):
        return "unavailable"
    finally:
        app.disconnect()
        if thread:
            thread.join(timeout=1)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args(argv)
    # Never echo API errors, accounts, usernames or arbitrary exceptions.
    logging.disable(logging.CRITICAL)
    status = "monitor_error"

    def timed_out(*_):
        raise TimeoutError("API handshake timed out")

    try:
        settings = load_config(args.config).ibkr
        signal.signal(signal.SIGALRM, timed_out)
        signal.alarm(TIMEOUT)
        status = probe(settings)
    except TimeoutError:
        status = "unavailable"
    except Exception:  # noqa: BLE001 -- errors become a fixed code, never private API/config text
        status = "monitor_error"
    finally:
        signal.alarm(0)
    print(json.dumps({"version": 1, "status": status}))
    return 0 if status == "healthy" else 1


if __name__ == "__main__":
    raise SystemExit(main())
