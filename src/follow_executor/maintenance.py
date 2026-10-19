# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Follow Executor contributors
"""Explicit, recoverable release switches. Never restore a trading journal."""
from __future__ import annotations

import hashlib
import json
import shutil
import uuid
from contextlib import ExitStack
from datetime import UTC, datetime
from pathlib import Path

from . import gateway, gateway_docker
from .config import ConfigError
from .local import exclusive, private_write
from .maintenance_state import backup_journal, journal_snapshot
from .release import verify_release


def record_path(wizard):
    return wizard.state / "maintenance.json"


def read_record(wizard):
    path = record_path(wizard)
    return json.loads(path.read_text()) if path.exists() else None


def require_complete(wizard):
    saved = read_record(wizard)
    if saved and saved["phase"] == "pending":
        raise ConfigError("A release switch was interrupted. Run './follow-stack rollback' to restore the "
                          "previous service definitions; trading must stay stopped.")


def configuration_hash(directory):
    digest = hashlib.sha256()
    for path in sorted(directory.rglob("*")):
        if path.is_symlink():
            raise ConfigError("Review configuration symlinks before maintenance.")
        if path.is_file() and not path.name.endswith(".lock"):
            digest.update(str(path.relative_to(directory)).encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()


def assert_unchanged(wizard, record):
    if (str(wizard.config) != record["config"]
            or configuration_hash(wizard.config.parent) != record["configuration_sha256"]
            or journal_snapshot(wizard.current_config())["journal_sha256"] != record["journal_sha256"]):
        raise ConfigError("Configuration or trading history changed during maintenance. "
                          "Review manually; no journal backup will be restored.")


def pending_restore(wizard, record):
    from .stack import Stack, command, service_state

    wizard.require_idle()
    if service_state(gateway.SERVICE) not in ("inactive", "failed"):
        raise ConfigError("Stop Gateway before recovering the interrupted release switch.")
    gateway_docker.require_stopped(wizard.config)
    backup = Path(record["backup"])
    if not backup.resolve().is_relative_to(wizard.state / "maintenance"):
        raise ConfigError("Invalid maintenance backup location.")
    source = Stack(Path(record["from_release"]))
    target = Stack(Path(record["to_release"]))
    verify_release(source.release)
    # Only restore our own known service; never overwrite a different installation.
    try:
        source.require_gateway_ownership()
    except ConfigError:
        target.require_gateway_ownership()
    with ExitStack() as locks:
        locks.enter_context(exclusive(wizard.config.with_suffix(".json.lock")))
        current = wizard.current_config()
        locks.enter_context(exclusive(current.journal_path.with_suffix(current.journal_path.suffix + ".lock")))
        locks.enter_context(exclusive(wizard.gateway_dir / "gateway.lock"))
        assert_unchanged(wizard, record)
        if input("Type ROLLBACK to restore the previous stopped services (keep the current journal): ").strip() != "ROLLBACK":
            return 3
        for name, destination in (("executor.service", wizard.unit_path), ("gateway.service", wizard.gateway_unit),
                                  ("container.image", wizard.pin)):
            private_write(destination, (backup / name).read_text())
        command(["systemctl", "--user", "link", str(wizard.unit_path)])
        command(["systemctl", "--user", "daemon-reload"])
        assert_unchanged(wizard, record)
        record["phase"] = "restored"
        private_write(record_path(wizard), json.dumps(record, indent=2) + "\n")
    print(f"Previous services restored and stopped. Journal and halts retained. Continue from {source.release}.")
    return 0


def switch(wizard, source_path: Path | None = None, *, rollback: bool = False) -> int:
    from .stack import Stack, command, docker_access, host_check

    host_check()
    docker_access()
    saved = read_record(wizard)
    if saved and saved["phase"] == "pending":
        if not rollback:
            require_complete(wizard)
        return pending_restore(wizard, saved)
    if rollback:
        if not saved or saved["phase"] != "complete":
            raise ConfigError("No completed release switch is available to roll back.")
        source, target = Stack(Path(saved["to_release"])), Stack(Path(saved["from_release"]))
    else:
        source, target = Stack(source_path.resolve()), wizard
    if source.release == target.release:
        raise ConfigError("Keep the new and retained releases in separate permanent directories.")
    source_meta, target_meta = verify_release(source.release), verify_release(target.release)
    if source_meta["compatibility"] != target_meta["compatibility"]:
        raise ConfigError("Journal/configuration or Gateway compatibility differs. This update needs a separately "
                          "reviewed migration; automatic switching is refused.")
    source.require_gateway_ownership()
    source.require_idle()
    if not source.pin.exists() or source.pin.read_text().strip() != source_meta["executor_image"]["id"]:
        raise ConfigError("The retained release does not match the installed executor image.")
    settings = gateway.load_settings(source.gateway_dir)
    if settings.get("backend") != "docker":
        raise ConfigError("Maintenance requires the container Gateway setup.")
    target.prepare_image(target.image_metadata(), changing=True)
    # This controller's verified probe supports maintenance even when rolling back
    # to a retained pre-maintenance wizard release. Compatibility above is exact.
    wizard.prepare_image(wizard.image_metadata(), changing=True)
    current = source.current_config()
    config_hash = configuration_hash(source.config.parent)
    verb = "ROLLBACK" if rollback else "UPGRADE"
    print(f"{verb}: {source_meta['executor_image']['id'][:19]} -> {target_meta['executor_image']['id'][:19]}")
    print("After a read-only flat-account check, Gateway will stop and both services will remain stopped.")
    confirmation = f"{verb} {current.ibkr.account_type.upper()} {current.quantity} {current.root}"
    if input(f"Type {confirmation} to continue: ").strip() != confirmation:
        return 3
    report = wizard.maintenance_report(wizard.image_metadata()["id"])
    if report.get("account_flat") is not True or report.get("orders_submitted") != 0:
        raise ConfigError("Complete read-only flat-account verification did not pass.")
    backup = wizard.state / "maintenance" / (datetime.now(UTC).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8])
    record = {"phase": "pending", "operation": verb.lower(), "backup": str(backup),
              "from_release": str(source.release), "to_release": str(target.release),
              "config": str(source.config), "configuration_sha256": config_hash,
              "journal_sha256": report["journal_sha256"], "halt_present": report["halt_present"]}
    with ExitStack() as locks:
        locks.enter_context(exclusive(source.config.with_suffix(".json.lock")))
        locks.enter_context(exclusive(current.journal_path.with_suffix(current.journal_path.suffix + ".lock")))
        assert_unchanged(source, record)
        backup.mkdir(mode=0o700, parents=True)
        shutil.copytree(source.config.parent, backup / "config", ignore=shutil.ignore_patterns("*.lock"))
        backup_journal(current, backup / "journal.sqlite3")
        for name, path in (("executor.service", source.unit_path), ("gateway.service", source.gateway_unit),
                           ("container.image", source.pin)):
            private_write(backup / name, path.read_text())
        private_write(record_path(wizard), json.dumps(record, indent=2) + "\n")
        try:
            command(["systemctl", "--user", "disable", "--now", gateway.SERVICE])
            gateway.require_stopped(gateway.SERVICE)
            gateway_docker.require_stopped(source.config)
            locks.enter_context(exclusive(source.gateway_dir / "gateway.lock"))
            target.install_image(target_meta["executor_image"]["id"])
            private_write(target.gateway_unit, target.gateway_unit_text(settings))
            command(["systemctl", "--user", "daemon-reload"])
            assert_unchanged(source, record)
            record["phase"] = "complete"
            private_write(record_path(wizard), json.dumps(record, indent=2) + "\n")
        except BaseException:
            print("Release switch incomplete. Both services must stay stopped; run './follow-stack rollback' to recover.")
            raise
    print(f"{verb} complete. Private backup: {backup}. Trading history and halts are unchanged.")
    print(f"Continue from {target.release}: ./follow-stack gateway start, approve login, ./follow-stack check,")
    print("then explicitly ./follow-stack start. Neither service was restarted by maintenance.")
    return 0
