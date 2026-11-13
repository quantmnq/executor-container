# Operations

English | [简体中文](OPERATIONS.zh-CN.md)

## Starts, stops and halts

`./follow start` checks readiness and enables the user service. `./follow stop`
disables it as well as stopping it, so it cannot unexpectedly resume on reboot.
Neither stopping nor disabling closes positions. Stop while flat for maintenance.
If you stop while holding a position, manage it through IBKR; locally timed
exits and stop adjustments no longer run.

`./follow status` reads the journal, not the current broker account. Use the IBKR
interface to verify actual positions and working orders. `./follow check` uses a
fresh broker snapshot, and must be run while the executor is stopped. `watch`
also needs the service stopped because a token supports one SSE connection.
A local process lock prevents overlapping run/check/watch/setup commands.

A halted executor continues repairing protection where possible. Inspect the
halt and the broker before `./follow resume`. Resume asks the running executor
to adopt current positions and align them with the target; that can submit an
exit. A new installation does not automatically adopt existing manual positions.

## Balance-sizing account values

With balance sizing, the running executor reads IBKR NetLiquidation once per
5-minute bar, 2:00 to 3:00 into the bar (US Eastern), during the Nasdaq cash
session: 09:30–16:00 ET, or 13:00 on early-close days, and never on weekends or
exchange holidays. It reads only while the last broker reconciliation found no
position and no working order. The read runs beside the trading loop, so it never
delays a signal, a stop move or the stop placed after a fill.

An entry uses that reading when it is at most 360 seconds old and no fill has
been recorded since it was taken. Otherwise the entry reads NetLiquidation
directly, as before. A restart or an IBKR reconnect discards the reading. The
journal log records each reading as `balance_reading` and each failure as
`balance_reading_failed`; a failed reading sends no alert. Each entry's
`balance_size` record shows `net_liquidation_source` (`mid_bar_reading` or
`direct_read`) with either `reading_age_seconds` or `reading_unused`, the reason
the reading was not used.

`./follow status` (or `./follow-stack status`) shows the latest read under
`sizing.account_value_health`: `status` is `ready` or `unavailable`, with its
`checked_at` time. Check the time as well as the status: reads pause while a
position is open and outside the cash session, so an old record does not prove
current readiness. Gateway handshake health alone does not establish
balance-sizing readiness.

If a read fails, an entry reuses the last sizing base when one exists and is
otherwise refused; the executor never guesses a size. Never reset the journal or
replay a refused signal to recover a missed trade.

With the bundled IBKR API version, the executor cancels each account-summary read
in the older message format. Gateway did not release subscriptions cancelled in
the newer protobuf format and refused further reads with IBKR error 322. Repeated
322 errors after an IBKR API upgrade need a new review.

## Settings and risk limits

`./follow configure` or `./follow settings` without options reruns the sizing
wizard if config exists: `balance` with a leverage fraction (previewing the
NQ/MNQ split at example weights at IBKR NetLiquidation), or a fixed `MNQ`/`NQ` quantity.
`./follow settings --leverage-fraction 0.5` or
`./follow settings --root MNQ --quantity 2` does the same from the command line.
The service must be stopped and Gateway must be reachable and logged in.
Existing positions, working orders, incomplete broker snapshots or a halt refuse
the change. Switching roots, or to or from balance sizing, checks both MNQ and NQ. The journal is preserved,
including finished trades, so a setting change does not erase replay protection.

Default maximum quantity is 10 contracts (hard maximum 100). To change the cap,
stop while flat and edit `risk.max_quantity` in your private configuration, then
use `settings` for the desired quantity. `risk.max_margin_fraction` (0.05 to
1.0) defaults to 1.0; before 0.4.2 it defaulted to 0.5, and configurations
written then keep their explicit 0.5 after an upgrade. To change it, stop while
flat and edit it in your private configuration. `risk.max_stop_risk_usd` can
impose an additional entry risk ceiling. These
settings are limits, not a recommendation for a suitable position size. NQ has
a different dollar multiplier from MNQ; the executor uses the selected root's
multiplier for its optional stop-risk calculation.

On first setup, `configure --advanced` allows a different relay, stream,
public key, Gateway host/port or client ID. Obtain the public key through a
trusted channel. Never store private keys or broker passwords in executor JSON.
The service uses the same fixed config path as `./follow`, independently of XDG
shell overrides; direct `follow-executor` commands also support `--config`.

The journal binds account, connection, stream, root and quantity. Direct edits
to those fields after setup are refused at run time: restore the old values,
then use the settings command. Normal size/root changes do not reset the journal.
If a disk failure interrupts a settings save and leaves a binding mismatch,
restore the previous configuration from your private backup before restarting;
do not erase the binding or journal to bypass it.

## Rotate the relay token

While stopped, replace the contents of
`~/.config/follow-executor/relay.token` in a local editor, keeping mode `0600`.
Run `./follow check`, then `./follow start`. The token must be a single nonempty
line. The token is separate from the config so it can be rotated without
changing account state. Never put it on a command line or in a Git commit.

## Paper to live, or another IBKR account

Do this only when flat, with no working orders. Verify both in IBKR, stop the
executor, run `./follow gateway stop`, and back up the config, token and journal
together in private storage (including local IBC credentials and Gateway settings).
To preserve isolation, move the entire `~/.config/follow-executor` directory and
`~/.local/state/follow-executor` directory to private backup paths. Do not delete
them. Recreate setup with `./follow configure`, select the new mode/account, and
rerun `./follow gateway configure` for that login and mode. Run
`./follow gateway start`, approve authentication, and complete `check` before `start`.
Moving configuration also moves the optional VNC password/startup files: if using
the desktop helper, stop it first and rerun `./scripts/gateway-desktop.sh` after
setup, or preserve those two desktop files in the config directory.

Never share one journal between accounts or run two instances with the same
account/client ID. Keep old account records; if a position remains, return to
its original setup and resolve it before switching. This is intentionally a
separate setup, not a live migration of open orders.

## Updates and backups

While flat with no working orders: `./follow stop`, `./follow gateway stop`, back
up private state, then
download and verify the next bytecode release. Extract it into its new version
directory and run its `./install.sh` to update both service paths. Run
`./follow gateway start`, approve any login prompt, then run `./follow check` and
`./follow start` there. Follow the [full setup guide](SETUP.md)
for download, verification, and rollback details. Installation does not overwrite
private config or the journal. Back up a stopped journal together with any SQLite
`-wal` and `-shm` files; preserve directory ownership and permissions. Do not copy
an old `.venv` into a new release or delete the journal during an upgrade.

The API source archive and SHA-256 are pinned in `scripts/install-ibapi.sh`.
IBC and native Gateway downloads are also checksum-pinned in their helpers.
A changed vendor download must be reviewed and released in a new package.
See [IBC operations](IBC.md) for credentials, scheduling and restart behavior. The customer bytecode release
requires CPython 3.12 on Ubuntu 24.04 ARM64; Python 3.13+ needs a new build.
