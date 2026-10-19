# Private Discord trade and service notifications

Combined `follow-stack` kit: follow [the beginner linking steps](SETUP.md#discord).
Use `./follow-stack discord ...` in place of the native `./follow discord ...`
examples below, and `./follow-stack setup` instead of `./follow configure`.
Trading start remains a separate explicit decision.

English | [简体中文](DISCORD.zh-CN.md)

AQ Bot sends personal **LONG**, **SHORT**, and **FLAT** notifications for this
executor's confirmed executions. LONG/SHORT shows the remaining contracts and
average entry price. Every FLAT message includes **Gross P/L in USD, before
commissions and fees**, for the complete round trip, including partial exits.
Stop placement, modification, cancellation and order-rejection messages are silent.
A stop that actually fills still changes the position and can produce FLAT.
Gateway, market-data, signal-feed and service-status alerts remain enabled.

Use customer package **0.1.7** with notification server **0.1.3 or newer**.
Existing customers must upgrade while flat and stopped using the
[setup guide](SETUP.md#update); keep the journal and notification database so
entry prices and notification history are retained. Existing Discord links remain
valid. Before upgrading, old packages still receive their legacy fill messages;
the server suppresses their stop/order-change messages immediately.

Your provider must deploy the notification service before these commands work.
Sign in to Discord (or create an account) and accept the provider's invitation to
the **Auto Quant** server. You do not need to create or host a bot.

After `./follow configure`, while the executor is stopped:

```bash
./follow discord link
```

Read the data-sharing explanation and type `LINK` to agree. The follower's Ubuntu
terminal then displays a one-time `code`. Using their own Discord account, the
follower opens `#bot-setup` in the **Auto Quant** server, selects **AQ Bot**'s
`/link` slash command, and enters that code in the `code` field. The code expires
after ten minutes. Submit it through the slash command, not as an ordinary chat
message. Never paste your relay token or IBKR credentials into Discord.

![Discord #bot-setup channel with AQ Bot's /link command and its code field](images/discord-bot-setup-link.png)

Replace the example `xxxxxxx` with the fresh code from **your own Ubuntu
terminal**. The screenshot shows the server owner's view; followers do not need
the **Edit Channel** button. [Full linking steps](SETUP.md#discord)

The bot replies privately to the command and sends a test DM. Allow direct
messages for Auto Quant and check Discord's message requests if necessary. Then:

```bash
./follow discord status
./follow discord enable
./follow check
./follow start
```

`enable` requires Discord to have accepted the test DM. Notifications start with
the next executor run; existing broker snapshot history is not sent as new trades
when notifications are first enabled. Linking alone does not start trading.

If Discord says **“The application did not respond”**, tell your Auto Quant
provider. The provider needs to check AQ Bot's saved interaction endpoint and
notification service. After the provider fixes it, run `./follow discord link`
again while the executor is stopped and submit the new code through AQ Bot's
`/link` command within ten minutes. Wait for the “Account linked” reply and test
DM before enabling notifications. A server configuration fix does not require
reinstalling your package. If linking succeeds but the DM does not arrive, check
your Discord privacy settings and message requests.

Examples:

```text
LONG — 2 MNQ.
Average entry: 20,150.25.
PAPER · MNQ 202612 · Order 7
IBKR execution time: 2026-10-14 14:30:45 EDT

FLAT — Closed 2 MNQ at 20,160.25 (average exit).
Gross P/L: +$40.00 USD
PAPER · MNQ 202612 · Order 8
IBKR execution time: 2026-10-14 14:45:00 EDT
```

P/L uses the recorded entry and exit executions for each contract, with
[MNQ's $2 per point](https://www.cmegroup.com/markets/equities/nasdaq/micro-e-mini-nasdaq-100.contractSpecs.html)
and [NQ's $20 per point](https://www.cmegroup.com/education/courses/introduction-to-equity-index-products/discover-equity-index-notional-value-and-price).
A positive result is profit, a negative result is loss, and `$0.00` is break-even.
It excludes commissions and fees. This is the executor's calculation, not IBKR's
net account P/L; it covers only this executor's recorded trades. Missing entry
history is explicitly marked unavailable instead of reporting an invented P/L.

Partial entries/exits can update LONG/SHORT and its remaining quantity; a partial
exit is not FLAT. A reversal closes one round trip before opening the opposite
side. IBKR corrections recalculate the affected trade and carry a `Correction:`
label. First enable/upgrade seeds existing history without announcing old trades.
Messages may be delayed, so verify current positions in IBKR.

Messages retain paper/live mode, contract month (or contract ID), broker order ID,
and execution time in **US Eastern time** (EDT in summer, EST in winter).
There is no `Observed:` line. If IBKR supplies a time without a usable timezone,
the time is marked unavailable; the trade notification still arrives.

## Gateway and service alerts

Release **0.1.2** adds these alerts automatically when Discord notifications are
enabled. The provider must run notification server **0.1.1 or newer** first.
Existing customers upgrade while flat and stopped using the [setup guide](SETUP.md);
their Discord link is preserved. The Sunday login default remains **12:00 noon
US Eastern**, following EST/EDT.

| Notification | What it means / what to do |
| --- | --- |
| Auto Quant service started / running | The process is operating. Gateway and signal readiness are checked separately. |
| IBKR Gateway outage | The API cannot be used. Check Gateway and approve IBKR Mobile if requested; inspect positions in IBKR. |
| Gateway reconnecting | Complete position, open-order and execution snapshots are still pending. A socket connection alone is insufficient. |
| Gateway needs attention | Account reconciliation or a safety check has not passed. Read the local halt reason. |
| Market data unavailable / refused / delayed | A farm or quote request failed, permissions or a competing session may prevent quotes, or only delayed/frozen data is available. |
| Market-data subscriptions not confirmed | Waiting for quote confirmation; this can happen when the market is closed. It is not labelled a confirmed outage. |
| IBKR Gateway recovered | Reconciliation passed and each monitored subscription has supplied both a live-data callback and a valid bid, ask or last price. |
| Gateway API ready, no contract selected | The API is reconciled, but there is no current contract to monitor. This does not claim that market data is ready. |
| Signal feed unavailable / recovered | Verified heartbeats stopped or the executor is behind; recovery requires heartbeats and catching up to the announced signal sequence. |
| Auto Quant halted / halt cleared | A safety halt needs review, or a deliberate recovery cleared it. A Gateway recovery does not clear a halt. |
| Execution-loop error / recovered | Order management encountered an error or successful loop iterations resumed. Check the logs and actual positions. |
| Auto Quant service stopped | Order management stopped; this does not close positions or cancel broker orders. |
| Auto Quant contact lost / restored | The relay stopped receiving service heartbeats, or contact resumed. It cannot identify whether the VM, process or network failed. |

Status changes are deduplicated across restarts. API outages and safety halts are
reported promptly; Gateway readiness and market-data errors must persist for five
seconds, and reconciliation/quote-waiting notices for 30 seconds. Repeated unchanged
states do not send repeated DMs. Notification delivery can still be delayed.

Quote monitoring is read-only, uses streaming subscriptions for the selected or
held contracts, and follows your existing IBKR market-data entitlements. It does
not purchase subscriptions or request paid regulatory snapshots. New subscriptions
must be confirmed after an API reconnect or a reported data-farm recovery. IBKR's
normal inactive/on-demand farm messages are not treated as failures. Quote silence
alone is not an outage alarm, so this does not detect every silent market-data
freeze. This monitoring does not change the signal-based order-pricing rules or
gate protective orders on notification delivery.

The service sends the relay a heartbeat about every **30 seconds** while its loop
is responsive. After **three minutes without a heartbeat**, the relay queues one
contact-loss DM; it queues another when contact returns. A stuck loop stops
renewing heartbeats after 60 seconds, so its alert can take roughly four minutes.
A normal stop reports that monitoring has stopped and suppresses a later missing-
heartbeat alert. A forced kill, VM loss or network failure cannot send that final
message; the relay's timeout covers that case after monitoring has first started.
Old installation versions have no heartbeat monitoring until upgraded.

Gateway health is observed while the executor is running. After an intentional
executor stop, no independent local Gateway watcher remains active. If the relay,
Discord or the bot itself is unavailable, that same path cannot deliver a timely
alert about its own outage. Use IBKR and the VM's logs to verify actual status.

Example recovery message (PAPER/LIVE is included):

```text
IBKR Gateway recovered: API reconciliation complete and live market-data subscriptions confirmed for the monitored contracts.
PAPER · MNQ
```

## For the server owner: create the setup channel

Create this channel once for all followers, using Discord on desktop or in a browser:

1. Open **Auto Quant**, click the server name at the top left, and choose
   **Create Channel** (or click **+** beside a channel category).
2. Select **Text**, enter `bot-setup` as the name without a leading `#`, leave
   **Private Channel** off, and click **Create Channel**.
3. Click the channel's gear icon → **Permissions**. Under **Advanced permissions**,
   select **@everyone** and enable **View Channel**, **Send Messages**,
   **Read Message History**, and **Use Application Commands** with the green checks.
   Click **Save Changes**.
4. In the same permissions panel, add/select the **AQ Bot** member or role,
   allow **View Channel** and **Send Messages**, and save.
5. Open `#bot-setup` and type `/link`. The command picker should show **AQ Bot**.
   Each follower supplies the code from their own Ubuntu terminal.

If the command is missing for a follower, open **Server Settings → Integrations →
AQ Bot** and check that the follower's role and `#bot-setup` can use `/link`.
Discord documents [channel permissions](https://support.discord.com/hc/en-us/articles/10543994968087-Channel-Permissions-Settings-101)
and [app command permissions](https://support-apps.discord.com/hc/en-us/articles/26501869403159-Command-Permissions).

The command response is visible only to the follower who invoked it. Test messages
and trade/service notifications arrive as DMs. `#bot-setup` is the recommended channel
name; the service also accepts `/link` in other permitted channels in Auto Quant.

## Privacy and delivery

Enabling this feature sends instrument, position, quantity, entry/exit prices, gross P/L, order
identifiers, service/Gateway status and times to Auto Quant's notification service
and Discord. Service heartbeats also disclose whether the follower is reachable. IBKR
credentials, account ID, relay token and the strategy source are not included in
messages. The relay token authenticates HTTPS requests to your configured relay;
it is not sent to Discord. Your provider stores the shared bot token only on its
server. Ordinary relay acknowledgements retain their existing limited fields.

Pending notifications are stored beside the journal in
`executor.notifications.sqlite3`. HTTP delivery runs outside the trading loop.
The service deduplicates event IDs and retries network errors and Discord rate
limits. Repeated broker snapshots do not normally produce repeated DMs. After a
long ambiguous Discord timeout or crash, a duplicate DM is still possible:
Discord's `nonce` deduplication has a limited time window. Delivery may be delayed
by outages or blocked DMs; a notification is not a substitute for the broker's
account statement. If notification storage fails, an error is logged and trading
continues. Check local and server logs for unresolved delivery errors.

To unlink, wait until flat, stop the service and run:

```bash
./follow stop
./follow discord unlink
```

Unlinking requires the notification service to be reachable. It cancels pending
server notifications and heartbeat monitoring for that subscription. Relinking creates a new recipient
binding, so old queued events cannot be sent to a newly linked Discord account.
Starting the executor again after unlinking runs without Discord notifications.
