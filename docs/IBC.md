# IBC: scheduled Gateway login and mobile approval

English | [简体中文](IBC.zh-CN.md)

This page describes the native backend. The optional [container pilot](GATEWAY_DOCKER.md)
uses the same private IBC configuration and schedule with a pinned upstream image;
follow that guide for installation, recovery desktop, data storage and upgrades.

The customer installer downloads **IBC 3.24.2** from its upstream release and
checks its SHA-256. The desktop helper downloads the pinned native **IB Gateway
10.51 ARM64** installer with bundled **Java 25**. IBC is a separate third-party
component. Installing it does not start Gateway or trading.

## 1. Install the private desktop and Gateway

Follow steps 1–5 in [SETUP.md](SETUP.md). Run the Gateway installer inside VNC,
accept IBKR's terms, and note its installation directory. Use a directory owned
by your Ubuntu user, normally `~/Jts/ibgateway/1051`. If the installer launches
Gateway, close that window before starting IBC. Keep the VNC desktop running.

IBC uses a separate persistent Gateway settings directory. Existing manual
Gateway settings are not imported. The first IBC login still needs inspection in
VNC for API settings, terms or other account-specific dialogs. Use IB API mode.

## 2. Configure IBC once

From the release directory, with the executor and Gateway stopped:

```bash
./follow gateway configure
```

The wizard asks for:

| Setting | Meaning |
| --- | --- |
| Gateway installation directory | Directory containing `jars` and `ibgateway.vmoptions` |
| Account mode | `paper` initially; if the executor is configured, its mode and port are reused |
| Schedule timezone | Default `America/New_York`; other IANA names include `UTC`, `America/Los_Angeles`, or `Asia/Shanghai` |
| Daily automatic restart | A 24-hour `HH:MM` time outside your active trading; default `23:45` |
| Sunday mobile approval time | A 24-hour `HH:MM` time when you can approve your phone; default `12:00` |
| IBKR login username/password | Hidden terminal input; use the login for the selected account mode |

The default schedule timezone is `America/New_York`: Sunday mobile approval is
at **12:00 noon US Eastern**, and the daily restart is at **23:45 US Eastern**.
Both follow EST in winter and EDT in summer. The VM's system timezone is not
changed. Previously saved schedules are retained when reconfiguring.
Both times use the selected timezone, including its daylight-saving rules. The
wizard checks Sunday times against IBKR's **Sunday 01:00 US Eastern** token reset
for the next two years and requires a 15-minute buffer. For example, `12:00 UTC`
is valid; a Sunday morning time in Asia may be too early. Ambiguous or nonexistent
Sunday times during clock changes are refused. Daily restart and Sunday login
must have different times. Choose times when a brief disconnection is acceptable.

For live mode, the wizard requires typing `LIVE`. Each customer supplies their
own credentials on their own VM; do not send them to Auto Quant or Discord.
Credentials are stored in `~/.config/follow-executor/gateway/ibc.ini` with mode
`0600`, inside a `0700` directory. Java property escapes are encoding, not
credential encryption. The VM user and root can read this file. Credentials are
not put in shell history, service arguments, the release archive, or relay requests.
Keep the containing directory and backups private.

## 3. Start Gateway and approve IBKR Mobile

```bash
./follow gateway start
./follow gateway logs
```

Approve the login notification in IBKR Mobile using your normal authentication.
IBC initiates login and can retry after a missed mobile prompt; it cannot approve
2FA for you. This workflow requires **IB Key / IBKR Mobile push authentication**.
Accounts that require passkeys, a code card, or other interactive methods may
still require VNC and are not supported as a phone-approval-only workflow.

Inspect the first login in VNC. Confirm the account mode, API port (**4002 paper**,
**4001 live**, unless your executor uses a custom port), and **localhost-only**
connections. IBC sets the API port, disables Read-Only API, and trusts
`127.0.0.1`; it rejects unexpected API-connection prompts. Do not expose the API
ports or VNC publicly. Complete any remaining IBKR notices yourself. If an auto-restart confirmation
appears, click **OK** once so the initial configuration can finish. If another
trading session already exists, this setup does not force it offline: close that
session deliberately, then restart this Gateway while the executor is stopped.

Follow the [Gateway API settings walkthrough](SETUP.md#gateway-api) for the exact
clicks. Gateway enables API connections automatically, so a missing
“Enable ActiveX and Socket Clients” checkbox does not prevent setup.

IBC renames Gateway's original launcher to control automatic restarts. After
setup, start Gateway with `./follow gateway start`, not its old desktop shortcut.
Ctrl-C exits the log viewer; it does not stop Gateway.

After login, continue the main guide with `./follow configure`, Discord linking,
then `./follow check` and `./follow start`. Gateway login alone does not start
trading. If you selected a different mode/port during executor configuration,
stop Gateway and rerun its configuration so both agree.

## 4. Weekly and daily behavior

The user service starts Gateway after the private desktop is available, including
after a VM reboot. A fresh login can produce a mobile approval prompt after any
restart; complete it before trading is needed. Daily automatic restarts normally
reuse the current session. On Sunday, IBC's `ColdRestartTime` starts a full login
at the chosen time, and the follower approves the phone notification. Changing
this appointment does not change IBKR's server-side token-expiry schedule.
IBKR may require authentication at other times too.

If you miss the prompt, IBC retries when the authentication attempt times out.
Do not approve an unexpected login without checking it. To stop repeated attempts,
stop the executor safely while flat and then stop the Gateway service.

| Command | Purpose |
| --- | --- |
| `./follow gateway status` | Show mode, port, timezone, schedule and process state, without credentials |
| `./follow gateway logs` | View IBC startup and authentication logs |
| `./follow gateway stop` | Stop Gateway and disable its autostart; refuses while the executor service is running |
| `./follow gateway start` | Enable autostart and start Gateway |

A running process is not proof of successful authentication. Confirm readiness
with `./follow check` while the executor is stopped. Gateway downtime interrupts
the executor's ability to submit or adjust orders. Stopping either service does
not close positions or cancel broker orders.

## 5. Change the schedule or credentials; upgrade

Wait until flat with no working orders and then run:

```bash
./follow stop
./follow gateway stop
./follow gateway configure
./follow gateway start
```

The wizard shows your existing schedule as defaults and asks for credentials
again. Approve the phone prompt, then run `./follow check` and `./follow start`.
Do not change the account or paper/live mode by editing `ibc.ini`; follow the
[account migration procedure](OPERATIONS.md) and configure both components.

For a package upgrade, stop both services and back up private configuration and
state. Install into the new release directory. Its installer downloads IBC and
refreshes the Gateway service path while preserving credentials, schedule and
Gateway settings. Run `./follow gateway start` from the new release, approve any
login request, then check/start the executor. Keep the old release until verified.

When upgrading a manual Gateway setup from version 0.1.0, the old release has no
`gateway` command. Stop the executor and close that Gateway manually while flat.
After installing the new package, complete steps 1–3 above to install the supported
Gateway version and configure IBC for the first time.

IBC/Gateway downloads are checksum-pinned. If IBKR replaces its download, the
helper will stop on a mismatch; request an updated Auto Quant package. Do not
bypass the checksum or replace IBC/Gateway with an untested version. The upstream
IBC repository was archived in September 2026; this integration uses its pinned
release, with compatibility review needed for future Gateway changes.

Validation of this release covers bytecode tests and opening the real ARM64
Gateway login window through IBC without credentials. Real mobile approval,
authenticated daily/weekly restart, and paper-trade recovery still need testing
with the follower's own account before live use.

References: [IBC release](https://github.com/IbcAlpha/IBC/releases/tag/3.24.2),
[IBC configuration](https://github.com/IbcAlpha/IBC/blob/3.24.2/resources/config.ini),
[IBKR weekly authentication](https://www.ibkrguides.com/traderworkstation/auto-restart-considerations.htm).
