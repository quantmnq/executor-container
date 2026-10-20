# Follower executor

English | [简体中文](EXECUTOR.zh-CN.md)

`follow-executor` mirrors the leader's `signal.v1` targets in **your** IBKR
account at **your** size. It runs on your machine next to your IB Gateway. The
leader never sees your credentials, account number, size or prices.

Start on an IBKR paper account. Use a live account only after the paper run
behaves as you expect.

## What it does

| Leader target | Executor |
| --- | --- |
| new position, before `entry.deadline` | margin check, then a marketable limit at `reference_price` ± `max_entry_slippage_points` (a market order if the price is null) |
| new position, after the deadline | stays flat for this trade |
| your entry fills | places a stop at once: `stop_atr` × `atr` from your fill |
| `protective_stop` known or moved | moves your stop to that price, up or down |
| `cancel_stop_at` reached | cancels your stop, on your own clock |
| flat | cancels the stop, waits for the cancel, then sends a market exit |
| feed lost at `flatten_at` | exits on its own 30 s after `flatten_at` |
| Gap→Drift continuation | keeps the position and moves the stop |

Rules that protect you:

- **One entry per trade.** If your stop fills, the executor never re-enters
  that trade, even inside the entry window.
- **A refused stop means exit.** If IBKR refuses a stop or a stop move, the
  stop level is treated as unreachable and the position is closed.
- **Stop protection deadlines.** For both long and short positions, if no
  broker-confirmed stop covers the actual filled quantity within **30 seconds**
  of observing an entry fill (including a partial fill), the executor starts a
  market exit. If an existing stop is cancelled or ceases to cover the position,
  it allows **60 seconds** for a matching replacement before starting the exit.
  A valid stop must be on the same contract, on the closing side, and have a
  remaining quantity exactly equal to the position. Pending submissions do not
  count as protection.
  Timers survive restarts and an expired deadline remains latched until flat;
  it does not re-enter that trade. Before sending an exit, the executor cancels
  outstanding orders and reconciles fills so it cannot deliberately reverse the
  position. These are exit-submission deadlines, not guaranteed fill times:
  broker disconnection, delayed confirmations or a closed market can delay the
  exit. An elapsed timer is handled after reconnection and reconciliation.
- **Verified pre-open cancellation.** If this executor deliberately cancels a
  matching stop under a signed `next_rth_open` plan, the scheduled exit deadline
  replaces the 60-second replacement deadline: `flatten_at` plus the configured
  exit grace, capped at **30 seconds**. For a 9:29 AM Eastern cancellation and
  9:30 AM exit, that means 9:30:30 at the latest. It requires a recorded request
  by this executor and broker confirmation that the stop is cancelled/absent;
  being near the opening time does not exempt a manual or unexpected cancellation.
  The plan must specify a one-minute cancellation window. A changed plan, new
  exposure or a replacement stop invalidates the old exception. Its fixed
  deadline survives restart and remains active during halts; an ordinary exit
  signal can still close earlier. The 30-second entry rule is never exempted.
- **Stops while flat.** Independently of normal trading and acknowledgement
  waits, the executor checks for its own working stops on flat contracts, also
  during a halt or after restart. It confirms flatness with a fresh broker
  snapshot, cancels those stops and any pending entries on the same contract,
  and blocks new entries until cancellation/fills are reconciled. A temporarily
  delayed position callback is given the existing five-second mismatch grace.
  A manual close does not prevent orphan-stop cleanup. If a stop or entry fills
  during cancellation, only the resulting, verified executor-owned exposure is
  closed. It never submits a market order merely because the account is flat.
  Foreign-client orders cause a halt and require their owner's intervention;
  they are not cancelled through a global account-wide cancel.
- **Margin.** Before an entry, an IBKR what-if must show initial margin at or
  below `max_margin_fraction` of equity (default 0.5). It is cached for up to
  15 minutes. If the check fails or is unavailable, the entry is refused.
- **Optional stop-risk ceiling.** With `max_stop_risk_usd` set, the executor
  refuses an entry whose size × multiplier × stop distance exceeds it.
- **Dedicated account.** The executor owns your chosen root (NQ or MNQ) in
  the account. It halts if it finds a position or working order on that root
  that it did not create.

## Halts

A halt stops all new exposure. Broker stops stay in place, and a missing stop
on a held position is still repaired. The protection deadlines above remain
active during a halt; an unexplained position or order must be reconciled before
an automatic exit can safely proceed. The executor halts when:

- your broker position differs from its own record of fills for more than
  5 s;
- an order on the root was not placed by this executor;
- an order is unacknowledged for 5 s;
- an exit is rejected;
- the position exceeds `quantity`;
- the configured account is not managed by the Gateway login.

To resolve a halt, inspect `./follow status`, fix the account (for
example, flatten a manual trade), then run `./follow resume`. Resume
makes the executor take ownership of the broker's current position on that
root. It then aligns that position with the latest target, which may close
it.

## Installation and operation

Follow the [complete customer setup](SETUP.md) and [OCI ARM guide](OCI_ARM.md). Use
`./follow configure` for setup and `./follow settings` for verified changes while
flat. The official IBKR API is installed by `./install.sh`; IB Gateway login and
periodic re-authentication remain with the follower.

`./follow check` verifies relay access, signatures, clock skew, the Gateway
account, positions/orders and what-if margin when the latest target carries a
contract month. A flat target can omit that month; in that case the preflight
cannot estimate margin, and the executor checks it at entry. The check never
transmits an executable order (IBKR what-if requests are simulations).

## Configuration

| Key | Default | Meaning |
| --- | --- | --- |
| `relay_url` | — | `https://relay.quantmnq.com` |
| `stream` | — | `sessioncycle.mnq` |
| `leader_public_key` | — | the leader's Ed25519 key |
| `token_path`, `journal_path` | — | absolute paths |
| `ibkr.port`, `ibkr.account`, `ibkr.account_type` | — | `paper` needs a `D…` account, `live` a non-`D` one |
| `ibkr.client_id` | 71 | keep it fixed: orders can only be modified by the client that placed them |
| `instrument.root`, `instrument.quantity` | — | `NQ` or `MNQ`, and your size |
| `risk.max_quantity` | 10 | a cap on `quantity` (at most 100) |
| `risk.max_entry_slippage_points` | 10 | limit-price cap when `reference_price` is present |
| `risk.max_margin_fraction` | 0.5 | initial margin after entry ÷ equity |
| `risk.max_stop_risk_usd` | null | optional ceiling on size × multiplier × stop distance |
| `feed.clock_exit_grace_seconds` | 30 | delay before the exit-plan fallback |
| `feed.heartbeat_timeout_seconds` | 30 | when to warn about a silent leader |
| `feed.send_acks` | true | send status acknowledgements to the relay |

## What the leader sees

With `send_acks`, the executor posts small acknowledgements to the relay:

- signal received;
- an order submitted, filled or rejected, by purpose (entry, stop or exit);
- entry missed or refused, with a reason code;
- a halt, with a reason code;
- once a minute, your direction (flat, long or short), whether it matches the
  target, whether you are halted, and the heartbeat age.

They never include your account number, quantity or prices.

The optional [Discord notification service](DISCORD.md) uses a separate endpoint
and requires account linking and consent to share quantity and execution/stop
prices, service health and liveness heartbeats. It does not change these acknowledgements.

## Files

- `~/.local/state/follow-executor/executor.sqlite3` is the journal: signals, trades,
  orders, fills, halts and a log. Keep it. Deleting it while holding a position
  makes the next start halt on an unexplained position.
- `./follow status` summarizes it.
