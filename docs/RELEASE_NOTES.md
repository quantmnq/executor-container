# Auto Quant 0.1.12 — position protection safeguards

English | [简体中文](RELEASE_NOTES.zh-CN.md)

Prepared October 19, 2026 (US Pacific). This candidate adds position-protection
safeguards, retains GPL source delivery and Gateway credential isolation, and
updates the English and Simplified Chinese beginner guides to this release.
Preparing this package does not publish it or update an existing installation.

## New in 0.1.12

- After observing an entry fill, including a partial fill, the executor allows
  **30 seconds** for a broker-confirmed stop covering exactly the held quantity
  in the correct direction and contract. If protection is still missing, it
  starts emergency closing after order/position reconciliation.
- Unexpected cancellation, loss or mismatch of an established stop allows
  **60 seconds** to restore protection before emergency closing.
- A verified strategy-requested stop cancellation in the one-minute window
  before a scheduled market-open exit uses that scheduled exit deadline, plus
  at most **30 seconds** of exit grace. It does not receive another 60 seconds.
  An unexpected cancellation or missing entry stop does not qualify.
- When a fresh, complete broker snapshot confirms a flat position with an
  executor-owned stop still working, the executor cancels the leftover stop
  and blocks new entries until reconciliation finishes. Cleanup also runs while
  halted. If an owned order fills during cleanup, verified resulting exposure
  is closed. Unrelated accounts' or other clients' orders are not adopted.
- Protection deadlines and cleanup state survive executor restarts. Emergency
  closing reconciles existing exits and fills to avoid duplicate closing orders.
- The example JSON uses `max_margin_fraction: 1.0`, as requested. This does not
  change the wizard default or an existing customer's settings.

These safeguards need a running executor and a working broker connection.
Disconnects, delayed confirmations or a closed market can delay actual closing;
30/60 seconds are protection deadlines, not guaranteed fill times.
See [execution and safety behavior](EXECUTOR.md).

## Retained from 0.1.11

- Customer executor, setup/build tools and original documentation are GPL-3.0-or-later.
- Every kit includes matching application source and notices; dependency source is offered beside the container download.
- The public source export excludes Git history, private release evidence and machine state.
- IBKR API archive-level license and third-party notices are preserved in the image.
- Signal-service implementation and provider strategy remain separate and private.

See [source and rebuilding](SOURCE.md).

## Retained from 0.1.10

Executor containers now obscure the managed Gateway credentials and maintenance
backup folders behind empty read-only mounts. Protection applies to commands,
maintenance probes and generated services. Setup and trading files retain their
paths; token/journal/CA settings pointing into protected directories are refused.
Old service definitions must be regenerated while stopped and flat. An image
change alone is insufficient. See [isolation and upgrade scope](EXECUTOR_DOCKER.md#credential-isolation).

Real Docker tests use synthetic credentials and disabled networking, verify
blocked reads/writes and mount-removal attempts, and exercise setup, settings,
Discord configuration and service replacement. Host secret fixtures remain
unchanged; the old launcher fails the same isolation check as expected.
This candidate has not replaced the running pilot or been published.

## Included

- A combined Gateway/executor setup wizard for Ubuntu 24.04 ARM64 and Python 3.12.
  An AI assistant is optional; no host Java, venv or full desktop is required.
- A bundled, immutable executor image and an upstream Gateway image pinned by
  digest. The Gateway version remains 10.51.1c.
- Private terminal configuration, resumable setup, signed relay/account/quote
  readiness checks and explicit confirmation before trading starts.
- One automatic fresh login after a five-minute unanswered Mobile request and a
  60-second restart delay; a second timeout stops for user attention.
- Authenticated API monitoring, restart after ten consecutive unavailable probes,
  and a persistent 30-minute cooldown. Monitoring pauses during authentication.
- Persistent trading history, reconciliation and halt retention, plus compatible
  release upgrade/rollback while stopped and flat.
- English and Chinese setup, recovery and operation guides.

Version 0.1.9 replaces the main SETUP guides with a first-time terminal workflow:
Windows/Mac terminal basics, local versus remote commands, file transfer/checksum,
Docker reboot/resume, private inputs, optional Discord and explicit paper start.
Native instructions remain separately available. The Chinese guide explains the
program's English prompts; the command-line interface itself remains English.

The protection logic above changes trading behavior relative to the accepted
0.1.7 pilot. Dependencies and the Gateway image remain pinned; older artifacts
remain unchanged. A first-time customer's independent completion of these
rewritten guides has not yet been observed.

## Where downloads come from

| Component | Download source |
| --- | --- |
| Auto Quant kit and matching checksum | Auto Quant's approved customer channel; Discord may carry the files or a download link |
| Docker Engine | Docker's official Ubuntu apt repository, `download.docker.com`; installed by the wizard if needed |
| Gateway container | Pinned `gnzsnz/ib-gateway` image from `ghcr.io`; downloaded directly on the customer's VM |
| Executor container | Included in the Auto Quant kit and loaded locally; customers do not build it or log into a registry |

Docker Engine is installed on the Ubuntu VM. Docker Desktop on the customer's
laptop is not required. Initial setup needs internet access for the external
downloads and broker/relay connections. After the first Docker installation,
reboot when instructed, reconnect and rerun `./follow-stack setup`.

## Validation and scope

The new protection paths are covered by automated broker fixtures, including
partial fills, restart persistence, scheduled cancellation, manual flattening,
halted cleanup, delayed callbacks and cancellation/fill races. The container
regression suite runs these tests against the installed bytecode with networking
disabled. These new paths have not yet been exercised against a real IBKR paper
account; the earlier pilot results below apply to the earlier implementation.
No account login, executable order or service deployment is part of this rebuild.

The preceding ARM64 pilot passed paper entry/protective-stop/exit, journal and
reconnect recovery, Docker interruption, host reboot, daily and Sunday restarts,
authenticated account checks and quotes. Fresh-OS bootstrap/reboot and
authenticated clean-user setup were tested separately; this was not a single
complete authenticated installation on a fresh VM.

On October 18 Pacific time, an isolated live authentication test received a new
Mobile notification after one automatic retry. The customer approved it; login,
two read-only API reconnects and the packaged health monitor passed. No live
orders, cancels or what-if orders were submitted. Live quotes and live trading
were outside scope. This successful run does not guarantee every future phone
notification will arrive; manual recovery remains documented.

The API-failure restart and cooldown were exercised through actual systemd with
simulated failures and accelerated polling. No real broker outage was injected.
The monitor checks authenticated API access; full readiness additionally checks
quotes, relay access, margin and reconciliation.

## Installation and updates

Use [the beginner setup guide](SETUP.md); [maintenance and recovery](CONTAINER_SETUP.md)
remain in the technical reference. Setup leaves trading stopped.
Review readiness, account mode, instrument and quantity before explicitly running
`./follow-stack start`.

Keep releases in separate permanent directories and preserve configuration,
Gateway data and the trading journal. Existing native installations need a
reviewed migration. Container upgrades use the compatibility and flat-account
checks in the guide; a version number alone does not establish compatibility.
Initial customer rollout is planned for a small
paper-account cohort on Ubuntu 24.04 ARM64. AMD64 is outside this release's scope.
