# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Follow Executor contributors
"""Ed25519 verification of the leader's signal envelopes."""

from __future__ import annotations

import base64
import hashlib
import json
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


class Verifier:
    """The leader's public key for one stream, as printed by signal-keygen."""

    def __init__(self, public_key: str) -> None:
        raw = base64.b64decode(public_key)
        self.key_id = hashlib.sha256(raw).hexdigest()[:16]
        self._key = Ed25519PublicKey.from_public_bytes(raw)

    def verify(self, envelope: Any) -> dict[str, Any]:
        if not isinstance(envelope, dict) or not isinstance(envelope.get("payload"), str):
            raise ValueError("envelope must carry a payload string")  # noqa: TRY004 - client input is HTTP 400
        if envelope.get("key_id") != self.key_id:
            raise ValueError("envelope was signed by a different key")
        try:
            self._key.verify(
                base64.b64decode(str(envelope.get("sig", ""))),
                envelope["payload"].encode("utf-8"),
            )
        except (InvalidSignature, ValueError) as exc:
            raise ValueError("envelope signature is invalid") from exc
        payload = json.loads(envelope["payload"])
        if not isinstance(payload, dict):
            raise ValueError("envelope payload must be an object")  # noqa: TRY004 - client input is HTTP 400
        return payload
