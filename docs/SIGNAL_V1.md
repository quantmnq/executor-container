# `signal.v1` for followers

English | [简体中文](SIGNAL_V1.zh-CN.md)

This is the follower's copy of the leader's event contract. The leader
(oci-quant) owns the authoritative version; this copy describes only what a
follower receives and may rely on.

## Delivery and authenticity

The relay serves Server-Sent Events at
`GET https://relay.quantmnq.com/v1/streams/sessioncycle.mnq/events` with your
personal token in `Authorization: Bearer <token>`.

- With `Last-Event-ID: <seq>`, every later signal is replayed, then live ones
  follow. Without it, only the latest target is sent.
- Frames are `event: signal` (with `id: <seq>`) or `event: heartbeat`. Comment
  lines are keepalives.
- Every frame's data is an Ed25519 envelope
  `{"key_id", "payload", "sig"}`. Verify `sig` over the UTF-8 bytes of
  `payload` with the leader's public key **before** parsing `payload`. The
  relay cannot alter or invent an event.

Leader key for `sessioncycle.mnq`:

- public key `zesvLFF3vT/hPtfal4i+m6K35v+cO9x4+jOXFLH6Xp4=`;
- key ID `30e3aa1ba8fe5ca0`, the first 16 hex digits of SHA-256 of the raw
  key.

Heartbeats are signed too:
`{"schema": "signal.v1.heartbeat", "stream", "latest_seq", "sent_at"}`, about
every 5 s. A heartbeat proves that the leader's publisher is alive. It does
not prove the leader is trading, so exit plans matter.

## What an event says

Each event is the leader's complete current **target**, not a delta. A
follower that missed events converges on the latest one. Sequence numbers are
contiguous, starting at 1.

Example values below are synthetic.

```json
{
  "schema": "signal.v1",
  "stream": "sessioncycle.mnq",
  "seq": 2,
  "emitted_at": "2026-10-01T18:10:09.150110+00:00",
  "cause": "protective_stop_installed",
  "instrument": {"root": "MNQ", "exchange": "CME", "currency": "USD",
                 "contract_month": "202612", "last_trade_date": "20261218"},
  "target": {
    "position": "long",
    "leg": "drift",
    "entry": {"session": "2026-10-01",
              "signal_time": "2026-10-01T18:10:00+00:00",
              "deadline": "2026-10-01T18:11:07.157008+00:00",
              "reference_price": null, "atr": 20.25,
              "stop_atr": 2.0,
              "trailing": {"enabled": true, "activation_atr": 1.0, "distance_atr": 1.5}},
    "protective_stop": {"price": 30452.75},
    "exit_plan": {"rule": "next_rth_open",
                  "cancel_stop_at": "2026-10-02T13:29:00+00:00",
                  "flatten_at": "2026-10-02T13:30:00+00:00"}
  }
}
```

- `position` is `flat`, `long` or `short`. A flat target has no leg, entry,
  stop or exit plan.
- **No quantity.** Choose NQ or MNQ of `contract_month` and your own size.
  Both trade in the same index points on the same 0.25 tick, so every price
  applies to either.
- `entry.deadline`: a flat follower may not open this position after it.
  Joining late never opens a stale trade.
- `entry.reference_price`: the NQ close of the leader's completed decision
  bar, for capping your entry price. It is null for a position the leader
  adopted rather than entered, and was null on all live entries before
  2026-10-02.
- `entry.atr` × `entry.stop_atr`: the stop distance the leader sizes from its
  own fill. It is useful before the leader's absolute stop arrives.
- `protective_stop.price`: the leader's absolute stop. It is null until the
  leader's entry fill is known, and again after the pre-open cancellation.
  Move your stop to it in either direction.
- `exit_plan`: the leader's own clock exit, as a fallback if you lose the
  feed.
  - `next_rth_open`: cancel the stop at `cancel_stop_at` and flatten at
    `flatten_at`.
  - `session_close`: flatten at `flatten_at`.

## Causes

| Cause | Meaning |
| --- | --- |
| `entry` | a new position; `protective_stop` is still null |
| `protective_stop_installed` | the leader's stop is known |
| `protective_stop_tightened` | trailing move |
| `gap_drift_continuation` | a held Gap long becomes Drift: same position, new leg, entry, stop and exit plan; flat followers get a fresh deadline |
| `continuation_stop_repriced` | the continuation's stop changed |
| `preopen_stop_cancelled` | stop cancelled one minute before the regular open |
| `exit_started`, `exit` | the target is flat |
| `reconciled` | a correction, for example after the leader's stop filled |

The leader holds one position at a time and changes direction only through a
flat target. It rolls to a new contract month only while flat.
