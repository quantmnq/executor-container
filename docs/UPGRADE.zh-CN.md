# 从 0.1.12、0.2.0、0.3.0、0.3.1、0.3.2 或 0.4.0 升级到 0.4.1

[English](UPGRADE.md) | 简体中文

0.4.1 保留 0.3.0 的**余额仓位**：你选择领单方 6 倍余额仓位的杠杆比例 `f`（大于 0 且不超过 1），
每次新入场时，执行器根据你的 IBKR NetLiquidation 和每个信号为该笔交易携带的 `sizing.weight`（大于 0 且不超过 1），
交易 NQ 加 MNQ 余数。
详见[仓位计算](EXECUTOR.zh-CN.md#仓位计算)和[版本说明](RELEASE_NOTES.zh-CN.md)。

本指南适用于组合容器安装包 `follow-stack-…`。原生 `follow-executor-…` 安装需要经过审查的迁移，
请联系 Auto Quant。

**不必立即升级。** 0.2.0 会继续按固定数量交易：领单方仍发送 `next_rth_open` 退出计划
（在常规开盘前撤销止损并平仓），0.2.0 的开盘前保护依然有效；0.2.0 会忽略新的
`sizing` 字段，不会使用信号权重或你的账户余额。使用余额仓位时，0.4.1 读取账户净值不会耽搁信号和订单；
连续运行数周未重启的执行器还能从 0.4.0 的提速中获益。

## 从 0.3.0、0.3.1、0.3.2 或 0.4.0 升级

0.4.1 只改变余额仓位读取账户净值的时机；区间、杠杆比例、仓位计算公式和保护规则都不变。
此前的版本在空仓期间每 30 秒读取一次 NetLiquidation，且在执行器的交易循环中进行，因此 IBKR
响应缓慢时，信号和订单会被耽搁。0.4.1 在纳斯达克常规交易时段内、仅在空仓且没有活动订单时，
每根 5 分钟 K 线读取一次，时间为该 K 线开始后第 2:00 至 3:00 分钟，读取与交易循环并行进行。
入场时，如果该读数不超过 360 秒，且读取之后没有记录任何成交，则使用该读数；否则仍按原方式直接读取
NetLiquidation。见[账户净值读取](OPERATIONS.zh-CN.md#余额仓位的账户净值读取)。固定数量配置不读取账户净值，行为不变。

从 0.3.0、0.3.1 或 0.3.2 升级时还会获得 0.4.0 的改进。此前的执行器每一步都会把进程启动以来的所有成交重新记录一遍，
因此长时间运行时会随成交增多而变慢（500 笔成交后每步约 40 ms，2,000 笔后约 450 ms），
同时拖慢下单处理。0.4.0 在 2,000 笔成交时每步仍不到 1 ms，行情报价也不再触发额外的步骤。
执行器运行时，`./follow-stack gateway stop` 现在会拒绝执行，与容器指南原有的要求一致：
请先在空仓时停止执行器。`./follow-stack status` 对交易日志无法识别的合约显示 `UNKNOWN`，
不再将其略去。从 0.3.0 或 0.3.1 升级时还会获得 0.3.2 的修复：当前 Gateway 在两次账户净值
（NetLiquidation）读取后不再响应（IBKR 错误 322），0.3.2 修复了此问题，并在 `./follow-stack status`
的 `sizing.account_value_health` 中显示最近一次读取结果，见[账户净值读取](OPERATIONS.zh-CN.md#余额仓位的账户净值读取)。
从 0.3.0 升级时还会获得 0.3.1 的修复：`./follow-stack settings` 切换仓位方式时不再发生 IBKR
client ID 冲突（错误 326），安装向导允许重新输入恢复画面密码，说明 IBKR 错误 354
（未订阅行情），并在维护期间允许无关的多头股票持仓。交易日志、配置和 Gateway 代码与
0.3.0、0.3.1、0.3.2 及 0.4.0 完全相同，无需迁移。按下文步骤操作，将每个 0.2.0 路径替换为
`~/follow-stack-0.3.…-ubuntu24.04-arm64-cp312` 或 `~/follow-stack-0.4.0-ubuntu24.04-arm64-cp312`，并跳过第 6 步：
你的仓位设置（包括余额仓位）会保留。回滚到 0.3.0、0.3.1、0.3.2 或 0.4.0 也会保留余额仓位。

## 从 0.1.12 升级

0.1.12 到 0.2.0 的 Gateway 代码差异只有三条关于独立登录用户名的提示。
本修复仅允许经过核对的已发布 Gateway 字节码哈希对；交易日志和 Docker
Gateway 代码仍须一致，未知变更仍会被拒绝。可按下文步骤操作，将 0.2.0
目录替换为保留的 `~/follow-stack-0.1.12-ubuntu24.04-arm64-cp312`。
升级前须确认账户没有阻止维护的持仓或任何活动订单（见下文无关股票持仓的例外），并保持 Gateway 已登录。
账户模式、固定数量、凭据和历史保留；升级不会自动开始交易或选择余额仓位。

0.3.1 是首个包含此兼容性修复的安装包；v0.3.0 安装包会拒绝 0.1.12，请直接升级到 0.4.1。
不要修改校验和来绕过检查。

## 会保留什么

升级会保留你的配置、relay token、Gateway 登录文件及数据卷、交易日志、通知记录和已有的暂停状态。
它会私密备份配置，并一致地备份交易日志；替换执行器镜像，并重新生成两个服务定义。
它不会平仓、撤单或启动交易。

## 1. 检查账户持仓和活动订单

选择 IBKR 账户中**没有持仓、也没有活动订单**的时间，例如计划退出之后或周末。先在 IBKR 中确认，
然后在 **0.2.0 目录**运行：

```bash
cd ~/follow-stack-0.2.0-ubuntu24.04-arm64-cp312
./follow-stack status
```

必须看到 `"expected_positions": {}` 和 `"halt": null`。不要在交易进行中停止：停止后的执行器无法移动止损或执行定时退出。
如果执行器处于暂停状态，先按[运维指南](OPERATIONS.zh-CN.md)处理；升级会保留暂停状态。

## 2. 空仓时停止执行器

仍在 0.2.0 目录中：

```bash
./follow-stack stop
```

保持 **Gateway 已登录**；升级的只读空仓检查需要它。不要删除或移动 `~/.config/follow-executor`
或 `~/.local/state/follow-executor`。保留 0.2.0 目录：升级和回滚都会读取它。

## 3. 上传、校验并解压新安装包

按[安装第 3 步](SETUP.zh-CN.md#3-上传并校验安装包)将
`follow-stack-0.4.1-ubuntu24.04-arm64-cp312.tar.gz` 及其 `.sha256` 传到 Ubuntu，然后：

```bash
cd ~/Downloads
sha256sum -c follow-stack-0.4.1-ubuntu24.04-arm64-cp312.tar.gz.sha256
tar -xzf follow-stack-0.4.1-ubuntu24.04-arm64-cp312.tar.gz -C ~
cd ~/follow-stack-0.4.1-ubuntu24.04-arm64-cp312
```

必须显示 `OK`。解压到这个**新**目录，不要覆盖 0.2.0。

## 4. 安装新版本并重新生成服务

在 0.4.1 目录中：

```bash
./follow-stack upgrade --from ~/follow-stack-0.2.0-ubuntu24.04-arm64-cp312
```

它会校验两个安装包，在不下单、不撤单、不模拟订单的情况下检查整个账户的持仓和订单，
并要求你输入屏幕上显示的确认文字，例如 `UPGRADE PAPER 1 MNQ`（你当前 0.2.0 的数量）。
随后它会私密备份、停止 Gateway、安装 0.4.1 执行器镜像，并重写执行器和 Gateway 服务。
0.2.0 到 0.4.1 是经过审查的迁移：交易日志和 Gateway 代码不变，0.2.0 的设置可原样读取。
**两个服务都保持停止。**

如果提示切换中断，请按[维护恢复](CONTAINER_SETUP.zh-CN.md)处理。

## 5. 重新登录 Gateway

```bash
./follow-stack gateway start
```

在 IBKR Mobile 批准登录。只有登录对话框需要处理时，才使用私密 VNC 画面。

## 6. 选择杠杆比例

重新运行询问仓位的设置步骤：

```bash
./follow-stack settings
```

| 提示 | 回答 |
| --- | --- |
| Sizing `[MNQ]`（你当前的品种） | 输入 `balance`。若要保留 0.2.0 的固定数量，在此及下一个提示处直接按回车，设置不会改变。 |
| Leverage fraction of the leader's 6x band | 你选择的数字，大于 0 且不超过 1，例如 `0.5`。`1` 表示完全按领单方仓位。 |
| Approximate current NQ price, for the preview `(Enter to skip)` | 可选，例如 `21000`。 |

它会在 IBKR 中确认 NQ 和 MNQ 均为空仓，显示你的 IBKR NetLiquidation（IBKR 未提供时会询问大致余额）和示例权重下的 NQ/MNQ 数量，
然后保存 `"sizing": {"mode": "balance", "leverage_fraction": f}` 并替换 `instrument`。
没有交互终端时，可运行 `./follow-stack settings --leverage-fraction 0.5`。交易历史会保留，
已结束的交易不会重新入场。

如果某笔交易每笔订单需要的 NQ 超过 `risk.max_quantity`（默认 10）、数量取整为 0 张（例如基准为 1 个
MNQ 单位时权重 0.4），或余额不足一个 MNQ 单位，该笔交易会被拒绝入场且不发送订单；
预览和检查会将取整为 0 的权重标为 `no entry`。是否调整上限请与 Auto Quant 商定，不要为了通过检查而调高上限。

## 7. 运行就绪检查

```bash
./follow-stack check
```

必须返回 0、`"problems": []`（包括行情），并将 `leader_key_id` 与 Auto Quant 提供的指纹对比。
查看 `sizing` 部分：`leverage_fraction`、`net_liquidation`、各示例权重的 `book`（例如 `1 NQ + 7 MNQ`），
以及 `margin` 中的 `"allowed": true`。行情可能需要等市场开盘，届时再运行一次。

## 8. 启动

```bash
./follow-stack start
```

只有确认文字与你的选择一致时才输入，例如 `START PAPER BALANCE 0.5`。启动后可能立即提交模拟订单。然后：

```bash
./follow-stack service-status
./follow-stack status
```

在不再需要回滚之前，保留 0.2.0 目录。

## 回滚到 0.2.0 或 0.1.12

回滚到 0.3.0、0.3.1、0.3.2 或 0.4.0 时，停止且空仓后直接运行 `./follow-stack rollback`，无需改动仓位。0.2.0 和 0.1.12 无法读取余额仓位。停止且空仓时，在 0.4.1 目录中先改回固定数量，再回滚：

```bash
./follow-stack stop
./follow-stack settings --root MNQ --quantity 1
./follow-stack rollback
```

回滚会重新进行维护持仓／订单检查，保留当前交易日志，两个服务保持停止。之后在 0.2.0 目录中依次运行
`gateway start`、`check`，并明确执行 `start`。

### 维护期间的无关股票持仓

维护检查仍要求完整的全账户持仓和未完成订单快照。它允许无关的多头 `STK`
持仓，包括碎股奖励股票。任何品种的期货、空头股票、期权、未知合约类型以及所有活动订单
仍会阻止切换；缺少股票代码同样会阻止。此例外只适用于升级／回滚维护检查；交易就绪检查、
交易日志对账和启动检查不变。它不会平仓或撤单，切换成功后两个服务均保持停止。
由于允许的股票持仓意味着账户并非完全空仓，报告使用 `maintenance_ready` 而不是 `account_flat`。
