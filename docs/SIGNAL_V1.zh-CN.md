# 跟单端 `signal.v1` 协议

[English](SIGNAL_V1.md) | 简体中文

本文是领单方事件协议的跟单端副本。权威版本由领单方（oci-quant）维护；本副本仅描述跟单端会收到什么，以及可以据此作出哪些判断。

## 传输与真实性验证

中继通过以下地址提供服务器发送事件（Server-Sent Events，SSE）：
`GET https://relay.quantmnq.com/v1/streams/sessioncycle.mnq/events`。
请求需在 `Authorization: Bearer <token>` 中携带你的个人访问令牌。

- 携带 `Last-Event-ID: <seq>` 时，会先重放该序号之后的所有信号，再继续发送实时信号。不携带该字段时，仅发送最新目标，然后继续接收实时信号。
- 事件帧为 `event: signal`（包含 `id: <seq>`）或 `event: heartbeat`。注释行用于保持连接。
- 每帧的数据都是 Ed25519 签名封装 `{"key_id", "payload", "sig"}`。必须在解析 `payload` **之前**，使用领单方公钥验证 `sig` 是否对应 `payload` 的 UTF-8 字节。中继无法修改或伪造通过验证的事件。

`sessioncycle.mnq` 使用的领单方公钥信息：

- 公钥：`zesvLFF3vT/hPtfal4i+m6K35v+cO9x4+jOXFLH6Xp4=`；
- 公钥 ID：`30e3aa1ba8fe5ca0`，取原始公钥字节的 SHA-256 哈希值的前 16 个十六进制字符。

心跳同样带有签名，格式为 `{"schema": "signal.v1.heartbeat", "stream", "latest_seq", "sent_at"}`，约每 5 秒发送一次。心跳证明领单方的发布器仍在运行，但并不能证明领单方正在交易，因此退出计划仍然重要。

## 事件内容

每个事件都包含领单方当前完整的**目标状态**，而不是相对于上一状态的增量。错过事件的跟单端会根据最新事件调整到目标状态。序号从 1 开始，连续递增。

以下示例使用模拟数值。

```json
{
  "schema": "signal.v1",
  "stream": "sessioncycle.mnq",
  "seq": 2,
  "emitted_at": "2026-10-01T17:00:09.150110+00:00",
  "cause": "protective_stop_installed",
  "instrument": {"root": "MNQ", "exchange": "CME", "currency": "USD",
                 "contract_month": "202612", "last_trade_date": "20261218"},
  "target": {
    "position": "long",
    "leg": "drift",
    "entry": {"session": "2026-10-01",
              "signal_time": "2026-10-01T17:00:00+00:00",
              "deadline": "2026-10-01T17:01:07.157008+00:00",
              "reference_price": null, "atr": 20.0,
              "stop_atr": 4.0,
              "trailing": {"enabled": true, "activation_atr": 3.0, "distance_atr": 5.0}},
    "protective_stop": {"price": 30452.75},
    "exit_plan": {"rule": "next_rth_open",
                  "cancel_stop_at": "2026-10-02T13:27:00+00:00",
                  "flatten_at": "2026-10-02T13:28:00+00:00",
                  "minutes_before_open": "2"},
    "sizing": {"weight": 0.5, "target_leverage": 6.0,
               "add_max_leverage": 5.88, "hold_max_leverage": 6.6}
  }
}
```

示例中的时间和数值仅作说明，并非领单方的参数；请按每个信号中的值执行。

- `position` 为 `flat`（空仓）、`long`（多头）或 `short`（空头）。空仓目标不包含策略分支、入场信息、止损或退出计划。
- **不包含数量。** 你自行选择 `contract_month` 对应的 NQ 或 MNQ 合约及数量，或按下文的 `sizing` 计算数量。两者都使用相同的指数点数报价，最小变动单位均为 0.25 点，因此信号中的价格适用于两者。
- `entry.deadline`：超过该时间后，空仓的跟单端不得再建立本次持仓。延迟加入不会触发过期交易的入场。
- `entry.reference_price`：领单方已完成的决策 K 线对应的 NQ 收盘价，用于限制你的入场价格。如果该持仓是领单方接管的已有持仓，而非自行新建，该值为 null。2026-10-02 之前的所有实盘入场信号中，该值也为 null。
- `entry.atr` × `entry.stop_atr`：领单方相对于自己的成交价计算的止损距离。在领单方的绝对止损价尚未到达时，可使用该距离。
- `protective_stop.price`：领单方的绝对止损价。在领单方入场成交信息明确前，以及开盘前撤销止损后，该值为 null。跟单端应将止损移至该价格，无论是上调还是下调。
- `exit_plan`：领单方按时钟执行的退出计划，也是在信号流断开时使用的备用方案。
  - `next_rth_open` 表示在 `cancel_stop_at` 撤销止损，一分钟后在 `flatten_at` 平仓，时间略早于下一个美东 09:30 常规开盘；`minutes_before_open` 为平仓时间距该开盘的分钟数（字符串）。`before_next_rth_open` 是领单方曾短暂发布的等价名称；0.3.0 起的跟单端两者都接受，领单方发送 `next_rth_open`，使 0.2.0 跟单端继续正常工作。
  - `session_close` 表示在 `flatten_at` 平仓。
  - 始终按 `cancel_stop_at` 和 `flatten_at` 执行；`minutes_before_open` 仅供参考。
- `sizing`：在领单方当前的仓位方式下，所有非空仓目标都带有该对象；空仓目标和更早的事件没有它。
  - `weight`：本次交易的权重，大于 0 且不超过 1。每个信号都带有该笔交易的 `sizing.weight`，跟单端使用收到的权重。
  - `target_leverage`、`add_max_leverage`、`hold_max_leverage`：领单方的余额杠杆区间，目前为 6 倍，加仓上限 5.88 倍，重置上限 6.6 倍。
  - 一个单位为一张 MNQ（每指数点 2 美元）；一张 NQ 等于十个单位。领单方的基准为 `floor(6 × NetLiquidation / (2 × NQ 价格))` 个单位，并在该区间内保持；每笔交易为 `round(基准 × weight)` 个单位（取整为 0 时不交易），即 `units // 10` 张 NQ 加 `units % 10` 张 MNQ。
  - 忽略未知字段的跟单端（包括 0.2.0）不受影响。

## 事件原因

| 原因 | 含义 |
| --- | --- |
| `entry` | 新持仓；`protective_stop` 仍为 null |
| `protective_stop_installed` | 领单方的止损价已知 |
| `protective_stop_tightened` | 移动止损调整 |
| `gap_drift_continuation` | 已持有的 Gap 多头转为 Drift：保留同一持仓，更新策略分支、入场信息、止损和退出计划；空仓的跟单端会获得新的入场截止时间 |
| `continuation_stop_repriced` | 延续交易的止损价发生变化 |
| `preopen_stop_cancelled` | 在 `cancel_stop_at`（常规交易时段开盘前）撤销止损 |
| `exit_started`, `exit` | 目标为空仓 |
| `reconciled` | 状态校正，例如领单方止损成交后的校正 |

领单方同时只持有一个仓位，改变持仓方向时必须先经过空仓目标。只有在空仓时，才会切换到新的合约月份。
