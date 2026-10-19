# Gateway container pilot

English | [简体中文](GATEWAY_DOCKER.zh-CN.md)

This optional path replaces the manual Gateway installation and full Ubuntu
desktop with the upstream [gnzsnz/ib-gateway-docker](https://github.com/gnzsnz/ib-gateway-docker)
image. Auto Quant still runs through its existing bytecode package and service.
Use **Ubuntu 24.04 ARM64 and an IBKR paper account** for the pilot. An existing
compatible test machine is sufficient for account checks; OCI is not required.
Use a machine with trading stopped and no positions or working orders before
changing its Gateway setup. A clean VM is useful for installation and reboot
validation before wider rollout, but provisioning a new VM is optional.
Completed pilot results and current preparation status are recorded in the
[release notes](RELEASE_NOTES.md). Existing installations retain their backend
until deliberately migrated. This does not provision a VM or remove IBKR authentication.

## Install and configure

Complete steps 1–4 in [SETUP.md](SETUP.md), including archive verification and
`./install.sh`. Replace step 5 with the steps below. No Gateway installer or
`gateway-desktop.sh` is needed for this path.

1. In the release directory on Ubuntu, run:

   ```bash
   ./scripts/install-docker.sh
   ```

   This installs Docker Engine from Docker's official Ubuntu package repository,
   enables its service, and adds your Ubuntu login to the Docker group. Members
   of that group can administer the VM; use a dedicated customer VM. Existing
   conflicting container packages are not automatically removed. The supported
   engine is local, rootful Docker 28 or newer, without user-namespace remapping.

2. After the first installation, reboot the VM once (`sudo reboot`). Reconnect
   with SSH and return to the release directory. This refreshes permissions for
   both your login and the user service manager. Logging into a new shell alone
   may leave the existing service manager with its old groups.

3. Configure Gateway:

   ```bash
   ./follow gateway configure --backend docker --vnc
   ```

   The wizard downloads the pinned ARM64 image, asks for paper/live mode and your
   schedule, and saves credentials privately on this VM. Initial defaults remain
   **paper**, `America/New_York`, daily `23:45`, Sunday `12:00`. Preserve an existing
   schedule when resuming. Enter your IBKR username/password in your own terminal,
   never in chat or a support message.

   `--vnc` enables a private recovery screen for first-login inspection. Choose a
   separate password of exactly eight printable ASCII characters; this is the
   VNC protocol limit, and privacy depends on the SSH tunnel. It is not your IBKR
   password. Without `--vnc`, new container setups have the desktop disabled.
   Reconfiguration preserves the selected backend and desktop setting.

4. Start Gateway, then approve IBKR Mobile if requested:

   ```bash
   ./follow gateway start
   ./follow gateway status
   ```

   To inspect the login screen, run this on your own computer, substituting your
   SSH key location and VM address:

   ```bash
   ssh -i ./auto-quant.key -N -L 5901:127.0.0.1:5901 ubuntu@YOUR_OCI_PUBLIC_IP
   ```

   Leave that tunnel open. In your VNC viewer connect to **localhost::5901**
   (TigerVNC notation), or host `localhost`, port `5901`. Complete any IBKR notices
   or terms yourself. The screen contains Gateway without a full Ubuntu desktop.
   Use the [API screenshots](SETUP.md#gateway-api) to inspect the first login.
   Gateway's internal API port is **4002 paper / 4001 live**; custom host ports
   are translated by Docker. Do not change the internal port to a custom host port.

5. Continue at [step 6](SETUP.md#follower): configure your relay/account/quantity,
   optionally link Discord, then run `./follow check`. Review its result and
   explicitly choose `./follow start` to begin paper trading. Installing or
   starting Gateway alone does not start the executor.

Review the terms applicable to your IBKR account and software before using the
third-party image. The image is pulled from upstream; Auto Quant does not bundle
IBKR binaries in its installation archive.

## Daily operation and recovery

The existing `gateway start`, `stop`, `status`, and `logs` commands work for both
backends. `gateway start` enables startup at boot. The user service supervises
the container; Docker's separate container restart policy is deliberately off.
Stopping Gateway disables startup and stops its container, while preserving data.
Stopping is refused while the executor service is running. Neither stop command
closes broker positions or cancels orders.

`gateway status` shows the selected image, process state, desktop availability,
and settings-volume name. A running container is **not proof of login**.
`./follow check` verifies account access, positions/orders, relay signatures and
available what-if margin while the executor is stopped.

| Symptom | Next action |
| --- | --- |
| Docker unavailable / permission denied | Confirm Docker is installed and running, then reboot once after group membership changes |
| Waiting for login | Approve the expected IBKR Mobile prompt; inspect VNC if a dialog remains |
| Login needs attention after two attempts | When ready, run `./follow-stack gateway start` (or `./follow gateway start` for the separate kit), approve the new request, then check readiness |
| Regular username has multiple paper-trading users | While stopped and flat, configure the intended paper-trading username and corresponding password, retaining paper mode |
| Another IBKR session exists | Close it deliberately; this setup retains `secondary` session behavior |
| Live quotes denied with error 10197 | Log out of the competing live trading session, including IBKR Mobile if applicable, then recheck live quotes; a successful API connection alone is insufficient |
| Port 5901 already in use | Stop the old native desktop service while flat before using the container desktop |
| Gateway image differs from this release | Follow the deliberate upgrade procedure below; do not edit the digest by hand |
| Process running but check fails | Inspect the check result and private Gateway logs; container state alone is insufficient |

To enable or disable the recovery screen later, wait until flat with no working
orders, stop the executor and Gateway, and run
`./follow gateway configure --backend docker --vnc` or `--no-vnc`, respectively.
The wizard asks for credentials again. Then start Gateway, approve any required
login, check readiness, and deliberately restart the executor. Weekly phone
approval and occasional additional authentication are still required; see
[IBC scheduling](IBC.md).

The Docker launcher allows five minutes to complete a Mobile approval. If login
remains pending, it stops that Gateway and the service makes one fresh login after
60 seconds. Gateway may then spend additional time at `Authenticating...` before
showing the next approval dialog. That dialog does not confirm phone notification
delivery. Dismiss stale notifications and promptly approve the new one if received.
A second timeout stops Gateway with
`login_recovery.attention_required=true` in `gateway status`; it does not keep sending
requests. When ready to approve, an explicit `gateway start` resets this limit only
while Gateway is stopped. Service restarts and host reboots retain the limit.
Successful login clears it, and an already authenticated JVM is not restarted by
this timer. A later weekly JVM restart can begin a new approval window.

If no phone notification arrives, follow [IBKR's notification troubleshooting](https://www.ibkrguides.com/kb/en-us/article-3234.htm).
It includes a private manual challenge/response Client Portal login to resynchronize
notifications. Log out of Client Portal before retrying Gateway; never share the
challenge or response codes in chat or support logs.

The host owns this retry policy; it disables IBC's overlapping timeout-relogin loop
in the container's private copy, including when using older saved configurations.
Gateway service logs show filtered login/recovery events rather than raw IBC output.
The private `gateway/login-recovery.json` records the limit; do not delete or edit it
to bypass an attention state. These changes apply to newly built kits; an older
installed kit retains its original behavior until deliberately upgraded.

The same supervisor now monitors the authenticated API once a minute, starting
one minute after login. It uses reserved client ID **9701**, waits for the IB API
handshake and managed-account response, and privately checks the configured
account. It does not request quotes, read the trading journal, submit orders or
cancel orders. In the combined kit the probe uses the release's pinned executor
image with only the executor configuration mounted read-only; no trading process
is started. Keep executor and other API client IDs different from 9701.

Ten consecutive unavailable API probes request a Gateway restart. The supervisor
persists a 30-minute restart cooldown across service and host restarts. Monitoring
pauses during login and warm/weekly JVM restarts, discards old probe results, and
leaves the bounded Mobile retry in control. Stopping the Gateway also stops its
monitor; there is no independent timer to start it again. A probe/image error,
client-ID conflict or account mismatch reports attention in the service log and
`api_health` status instead of triggering a Gateway restart. Broker market-data
farm messages alone do not count as failed local API handshakes.

`gateway status` includes **cached** `api_health` results and their last-probe time;
an old healthy result does not establish current readiness. The API monitor does
not verify quote entitlement/freshness, relay access, margin or reconciliation.
Continue to use the full readiness check before explicitly starting trading.

For manual login recovery:

1. Inspect `./follow-stack gateway status` and `./follow-stack gateway logs`.
   If login already needs attention and Gateway is stopped, run
   `./follow-stack gateway start` when ready to approve.
2. If a login is stuck while Gateway is still running, first confirm the account
   is flat with no working orders in IBKR. Then run `./follow-stack stop`,
   `./follow-stack gateway stop`, and `./follow-stack gateway start`. These commands
   do not flatten an account or cancel its orders. If exposure remains and the
   API is unavailable, manage it through IBKR before planned maintenance.
3. Dismiss old notifications without approving them. Promptly approve only the
   new expected request; do not repeatedly use Resend. If none arrives, follow
   the linked IBKR troubleshooting and private recovery desktop instructions.
4. Run `./follow-stack check` with the executor stopped. After it passes, explicitly
   run `./follow-stack start` only if you intend to trade. For the separate kit,
   use `./follow` in place of `./follow-stack`.

The October 18 live acceptance test verified delivery and approval of a fresh
notification after one automatic retry, followed by authenticated API recovery.
Monitoring alone cannot guarantee future push delivery; retain the manual fallback.

## Private data, upgrades and switching back

Credentials remain in the private host `gateway/ibc.ini` file (mode `0600`). A
short, network-disabled initialization container copies it into a private Docker
volume for the image's user, UID 1000. This supports a different Ubuntu login UID
without making host credentials publicly readable. The running Gateway uses UID
1000, drops Linux capabilities, and disables privilege escalation. Passwords are
not passed as Docker environment variables or command arguments.

The Docker volume contains another copy of the IBC credentials, optional VNC
password, and persistent Gateway settings. It is sensitive, just like the host
configuration. `gateway status` prints its name. Do not send its contents to
support or remove it with Docker volume-pruning commands. Keep the executor's
configuration and SQLite journal in their existing locations; never reset the
journal to solve a container problem. API and VNC ports are published only on
`127.0.0.1`; no additional OCI inbound ports are needed.

An Auto Quant release pins an immutable image digest; starting Gateway does not
pull a new image. Updates to Docker Engine and Gateway are separate maintenance
actions, performed while flat with both services stopped. Keep the prior Auto
Quant release and image for rollback. Back up private host configuration, journal,
and the stopped Gateway volume using your private VM backup procedure.

When a release intentionally changes the image pin, stop both services and
reconfigure Gateway with that release to select its reviewed image. An old saved
pin is refused instead of silently replaced. If installer `gateway refresh`
reports this mismatch, run the new release's `gateway configure --backend docker`
and rerun the installer before starting. To roll back, use the retained release,
reconfigure its Gateway image, and verify readiness. Never restore a stale trading
journal; restore Gateway settings only from a compatible, stopped backup.

To return to native Gateway, stop both services while flat, prepare the native
installation in [SETUP.md](SETUP.md#gateway), then configure with `--backend native`.
If switching from native to Docker with VNC enabled, also disable the old desktop:
`systemctl --user disable --now follow-gateway-desktop.service`.
Native and Docker Gateway settings are separate; neither imports the other's
session. Keep the same executor configuration and journal, and verify the account
before starting again. Do not run both backends against one account.

## Maintainer acceptance checklist

The pinned image is Gateway **10.51.1c**, with IBC **3.24.2**:

- Index: `sha256:13229ab03b0f455bf41380172e69815b164f0b911345f471ccecdcff0cde90ca`
- ARM64 manifest: `sha256:b3e4ebc891c6668f050ccf7f782a8f883676407b090d06efb17d85b5d0da5520`
- Reviewed upstream source: `11d3eeb945f3cdfc4859dbe5a2c75acd18f18d53`.

Before making this the customer default, record results on the supported ARM64
environment, including a clean-installation and reboot check:

- First login, first-run dialogs, API settings, and successful account check.
- Missed mobile approval, retry, and existing-session handling.
- Authenticated daily restart and Sunday cold restart across the chosen timezone.
- VM reboot, Docker interruption, and Gateway process failure/recovery.
- Paper entry, broker stop, exit, reconnection, and absence of duplicate orders.
- Upgrade/rollback with persistent settings and the original executor journal.
- Private-input handoff and resuming the customer wizard after interruption.

For the 0.1.7 pilot, local validation used the real pinned ARM64 image and an
isolated Docker 29.8.2 engine. The test containers had networking disabled and
blank IBKR credentials. Gateway reached its login dialog; Java, the virtual
display and private credential-file permissions were verified. Settings survived
container removal/recreation, the engine accepted the loopback port mappings,
and an orphaned Gateway was recovered after its supervisor was forcibly killed.
The generated systemd unit passed verification. All 133 automated tests passed
against the installed bytecode wheel, with no application source installed.

On 2026-10-15, the distributed 0.1.7 package also passed an authenticated paper
pilot on an existing Ubuntu 24.04 ARM64 host using Docker 29.9.1. The expected
paper account, complete position/order snapshots, buy/sell what-if margin checks,
and live MNQ quotes were verified. Authenticated recovery passed after both a
graceful Gateway service restart and a forced supervisor failure; settings
survived container replacement. API reconnection succeeded with a five-second
delay before retrying.

One explicitly authorized paper cycle bought one MNQZ6, verified an acknowledged
broker stop exactly 20 points below the entry fill, reconstructed the executor
and broker objects from the same test journal, and reconnected without adding an
entry or stop. The exit filled, replaying the old entry did not re-enter, and an
independent complete broker snapshot confirmed zero positions and working orders.
This tested journal reload and API reconnect, not an executor OS-process crash.
The test used a separate journal and no production feed or notifications. The
original executor remained stopped, and its journal still matched its backup.

The pilot initially encountered error 10197 while a competing live session was
using market data; the customer identified IBKR Mobile. Live quotes were
confirmed before the cycle began. No automated session eviction was performed.
This is a customer onboarding checkpoint for either Gateway backend.

A subsequent Docker interruption check stopped both the daemon and its socket,
confirmed the API listener disappeared, and then restarted Docker. Recreating the
socket removed the shared host's temporary ACL, so the existing user service
manager could not access Docker until that ACL was restored. After this permission
repair, the Gateway supervisor automatically recreated the container and recovered
the authenticated paper account, complete flat snapshots, persistent settings,
and live quotes. The relay service processes and original executor journal were
unchanged. This verifies recovery with the pilot's permission workaround, not
unassisted recovery on a freshly rebooted customer host.

The October 15, 2026 daily restart occurred at 8:45 PM Pacific; authenticated API
access returned at 8:46 PM with the account flat. The observer did not pass its
full readiness check because a competing live session denied quotes (10197).
After the customer logged out of that session, a separate read-only check at
9:27 PM confirmed live quotes ready with no errors. This verifies scheduled
restart and authentication recovery, with manual resolution of the quote conflict.

On October 16 at 1:00 AM Pacific, the actual executor container passed a combined
paper cycle through this Gateway using a signed test feed. SIGKILL and automatic
executor replacement preserved its journal and original protective stop, with no
duplicate orders after event replay. The position was closed and the account was
flat. See [executor acceptance results](EXECUTOR_DOCKER.md#validation-status).

The full-host reboot check passed at 1:10 AM Pacific. Both containers returned,
authenticated account access and live quotes recovered without permission repairs,
and the user service manager had Docker group access without a socket ACL. Shared
services recovered; original executor configuration and journal were unchanged.
The flat-only test executor and feed were then stopped and disabled. This removes
the pilot's temporary permission workaround, but does not establish clean-host
installation acceptance.

The [unified customer wizard](CONTAINER_SETUP.md) now includes quote readiness and
explicit compatible-release upgrade/rollback. Its offline transaction tests cover
interrupted switching, retained halts and preserving newer trading history.
The October 17 fresh Ubuntu guest rehearsal also passed installation/reboot/resume
and actual Docker/systemd upgrade/rollback with a simulated account gate; see the
[wizard acceptance details](CONTAINER_SETUP.md#maintainer-build-and-acceptance).
Authenticated upgrade/rollback passed on October 18 using an isolated Linux test
user on the same OCI host, with real paper-account gates, preserved configuration
and journal, and trading stopped. A subsequent clean-user setup on the existing
OCI host passed paper login, real relay/account/margin checks and clock readiness
(0.6-second difference) using the unchanged packaged wizard. Its resumed wizard
still received no live quote. Fresh-OS bootstrap and authenticated clean-user checks
are separate evidence, not a full authenticated fresh-VM installation.
The tested paper username did not request Mobile approval; approval
timeout/retry recovery was tested separately in live mode, as recorded below.
An isolated live login on October 18 produced Mobile requests, but approvals after
manual resend failed with a phone-side server-communication error. A fresh login with
prompt approval subsequently passed live authentication and two fresh account-data
checks on separate API connections; Gateway confirmed API read-only mode. This verifies
manual fresh-login recovery, while genuine expiry and automatic retry were not established by that test.
The live test stopped without trading; the original paper Gateway remained authenticated
and flat. Live-account quotes and trading were not tested.
Subsequent tests found no automatic retry during 601.3 seconds with an untouched
request, or during 120 seconds after the customer attempted the original aged request
and reported an expiry/timeout error. No Resend or manual restart was used. The
authentication dialog remained open; IBC only evaluates this timeout when the dialog
closes. Automatic recovery did not pass these observed scenarios. Both tests stopped
without trading and preserved the authenticated, flat original paper Gateway.
The separate latest-image readiness check received no live quote.
The October 18 Sunday cold-restart check passed:
a healthy baseline was captured at 8:57 AM Pacific, a new JVM was observed at
9:00:10, and repeated complete, authenticated flat-account snapshots confirmed
recovery by 9:01:55. The observer submitted no orders and changed no services.
Live quotes were outside this check's scope. This confirms scheduled restart and
account recovery; the observer did not establish whether a fresh IBKR Mobile
challenge was required. The container remains an optional pilot, not the customer default.


Later on October 18, the new bounded login watchdog was tested twice using the
installed bytecode matching the local `0.1.7-login-recovery-pilot` image. Both runs
timed out the unanswered request after five minutes, restarted after 60 seconds,
and opened a second authentication dialog. When the second attempt did not
complete, the launcher exited with status 2 and retained `attention` with two
attempts used. In the first run the customer reported expiry/timeout, but was unsure
whether the new notification or an existing app screen was used. In the repeat the
first notification was dismissed without approval; no completed login was observed
before the cutoff. Automatic retry and retry exhaustion are verified. Authenticated
recovery was not verified in those runs; the earlier successful first-prompt live login and API
reconnection remain separate evidence. No live orders, cancellations, what-if orders
or trading executor were involved, and the original paper Gateway was preserved.

A further run at 3:46 PM Pacific timed out and restarted as expected. The second
Gateway spent about three minutes at `Authenticating...` before opening its second
factor dialog at 3:55:13. The customer confirmed that no new phone notification was
received. Login did not complete, and the attempt limit stopped the test at 4:00 PM.
That run left retry-notification delivery and authenticated recovery unresolved.
Opening the Gateway dialog does not verify push delivery; the cause is not established.
The original paper Gateway remained unchanged, authenticated and flat. IBKR's
[notification troubleshooting](https://www.ibkrguides.com/kb/en-us/article-3234.htm)
includes a manual challenge/response login to resynchronize notifications; that
customer-side diagnostic was then requested and completed before the later successful test below.

At 3:18 PM Pacific, the unchanged clean-user packaged wizard passed its remaining
paper quote check: live market data was ready with no quote error codes, all readiness
checks passed, and clock difference was 0.8 seconds. The original paper Gateway was
restored authenticated and flat, with configuration/journals unchanged and all
executors stopped and disabled. This completes the paper checks for the agreed
split validation approach; fresh-OS bootstrap and authenticated clean-user readiness
remain separate tests. At that point the new watchdog build was unpublished and had
not replaced the running pilot or become the customer default.


At 5:10 PM Pacific on October 18, the exact packaged API-monitor candidate passed
live automatic recovery. The customer had completed the private Client Portal
manual login and logged out. The first Mobile request was received and dismissed
without approval; after the five-minute limit and 60-second restart delay, Gateway
opened the next prompt at 5:07:26. The customer confirmed a new notification arrived
and approval succeeded. Gateway completed login, two read-only API connections
received fresh account data, and the packaged health monitor became healthy. There
was one automatic restart, no manual resend/restart, and no live orders, cancels,
what-if requests or trading executor. The isolated live Gateway was stopped and
the original paper setup was preserved. This verifies one coordinated recovery;
it does not establish the cause of earlier missing notifications or prove that the
Portal diagnostic alone fixed them. Live quotes and trading were outside scope.

At 5:11 PM Pacific, the candidate was activated locally through a reviewed paper
supervisor migration. Existing Gateway credentials, schedule and data volume were
retained; the verified clean-user paper config and journal were copied privately
without resetting history. The new monitor and packaged full readiness, including
quotes, passed. The paper account was flat with no working orders, all executors
remained stopped/disabled, and prior native/test configurations and journals were
preserved. Real systemd testing also verified restart after ten simulated API
failures, cooldown persistence, and no competing probes during authentication;
no real broker outage was injected. All agreed ARM64 paper and live-authentication
acceptance checks are complete. The kit remains unpublished and is not the customer
default. The activated archive is immutable; these later acceptance notes are in
the source guides and validation records.

Local automated tests cannot establish authenticated readiness. IBC's upstream
repository is archived; future Gateway updates still require compatibility review.
The upstream repository's MIT license covers its code; bundled software has its
own terms. Review those separately before redistributing or modifying an image.
The upstream notice for the adapted Gateway settings template is included at
[`licenses/ib-gateway-docker-MIT.txt`](../licenses/ib-gateway-docker-MIT.txt).

References: [upstream source](https://github.com/gnzsnz/ib-gateway-docker),
[Docker installation](https://docs.docker.com/engine/install/ubuntu/),
[IBKR market-data sharing](https://interactivebrokers.github.io/tws-api/market_data.html),
[IBKR weekly authentication](https://www.ibkrguides.com/traderworkstation/auto-restart-considerations.htm).
