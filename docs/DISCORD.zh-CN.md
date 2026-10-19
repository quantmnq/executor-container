# Discord 私人交易与服务通知

组合 `follow-stack` 安装包请按[零基础关联步骤](SETUP.zh-CN.md#discord)操作。
下方原生 `./follow discord ...` 命令改用 `./follow-stack discord ...`，
`./follow configure` 改用 `./follow-stack setup`。启动交易仍需单独明确决定。

[English](DISCORD.md) | 简体中文

AQ Bot 根据本执行器已确认的成交，发送 **LONG（多头持仓）**、**SHORT（空头持仓）** 和 **FLAT（已平仓）** 私信。LONG/SHORT 显示剩余合约数量和平均入场价。每条 FLAT 消息都包含整笔交易的 **Gross P/L（美元毛盈亏，未扣佣金和费用）**，包括分批平仓的结果。不再发送止损挂单、改单、撤单和订单拒绝通知。止损实际成交仍会改变持仓，完全平仓时会发送 FLAT。Gateway、行情、信号流和服务状态通知继续发送。

客户安装包 **0.1.7** 需要通知服务器 **0.1.3 或更新版本**。已有客户应在空仓且停止时，按[安装指南](SETUP.zh-CN.md#update)升级，并保留交易日志和通知数据库，以保留入场价及通知记录。Discord 关联会保留。升级前，旧包仍接收原有的成交通知；服务器会立即屏蔽旧包的止损及订单变更通知。

信号提供方必须先部署通知服务，以下命令才能使用。登录 Discord（或创建账号），并接受提供方的邀请，加入 **Auto Quant** 服务器。你无需创建或托管机器人。

运行 `./follow configure` 后，在执行器已停止的情况下运行：

```bash
./follow discord link
```

阅读数据共享说明，输入 `LINK` 表示同意。随后，跟随者的 Ubuntu 终端会显示一次性配对码 `code`。跟随者使用自己的 Discord 账号，打开 **Auto Quant** 服务器中的 `#bot-setup` 频道，选择 **AQ Bot** 的 `/link` 斜杠命令，并在 `code` 字段中填入该配对码。配对码在十分钟后过期。请通过斜杠命令提交配对码，不要将其作为普通聊天消息发送。切勿将中继访问令牌或 IBKR 登录凭据粘贴到 Discord。

![Discord 的 #bot-setup 频道：AQ Bot 的 /link 命令及 code 输入框](images/discord-bot-setup-link.png)

将示例中的 `xxxxxxx` 换成**你自己的 Ubuntu 终端**刚显示的关联码。截图使用服务器管理员视图，跟随者不需要点击 **Edit Channel（编辑频道）**。[完整关联步骤](SETUP.zh-CN.md#discord)

机器人会以仅你可见的方式回复命令，并发送一条测试私信。请允许接收来自 Auto Quant 服务器成员的私信；如有需要，也请检查 Discord 的消息请求。然后运行：

```bash
./follow discord status
./follow discord enable
./follow check
./follow start
```

`enable` 要求 Discord 已接受测试私信。通知会从执行器下一次运行时开始发送；首次启用通知时，不会把券商快照中已有的历史记录作为新交易发送。仅完成账号关联不会启动交易。

如果 Discord 显示 **“The application did not respond”（应用程序未响应）**，请联系 Auto Quant 提供方，让其检查 AQ Bot 已保存的交互端点地址及通知服务。提供方修复后，在执行器已停止的情况下重新运行 `./follow discord link`，并在十分钟内通过 AQ Bot 的 `/link` 命令提交新配对码。收到 “Account linked” 回复和测试私信后，再启用通知。服务器配置修复无需重新安装客户软件包。如果关联成功但未收到私信，请检查 Discord 隐私设置和消息请求。

示例（程序实际发送的英文消息）：

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

盈亏按每个合约记录的入场和平仓成交计算：[MNQ 每点 2 美元](https://www.cmegroup.com/markets/equities/nasdaq/micro-e-mini-nasdaq-100.contractSpecs.html)，[NQ 每点 20 美元](https://www.cmegroup.com/education/courses/introduction-to-equity-index-products/discover-equity-index-notional-value-and-price)。正数为盈利，负数为亏损，`$0.00` 为盈亏平衡，均未扣佣金和费用。这是执行器根据其交易记录计算的毛盈亏，不是 IBKR 账户净盈亏，也不包含与本执行器无关的交易。缺少入场记录时会明确标注盈亏不可用，不会猜测。

分批入场或平仓可能更新 LONG/SHORT 及剩余数量；仅部分平仓不会显示 FLAT。反向交易会先结束上一笔交易，再建立反向持仓。IBKR 成交更正会重新计算受影响交易，并标注 `Correction:`。首次启用或升级会载入历史记录，不会把旧交易当作新交易通知。消息可能延迟，请在 IBKR 核实当前持仓。

消息保留模拟/实盘模式、合约月份（或合约 ID）、券商订单 ID，以及**美国东部时间**的成交执行时间（夏季 EDT，冬季 EST），不再显示 `Observed:` 行。IBKR 时间缺少可用时区时会标注时间不可用，但交易通知仍会发送。

## Gateway 与服务状态通知

**0.1.2** 版本会在启用 Discord 通知后自动增加以下提醒。提供方需要先运行 **0.1.1 或更新版本**的通知服务器。已有客户按[安装指南](SETUP.zh-CN.md)在空仓且停止后升级，Discord 关联会保留。周日登录默认仍为**美国东部时间中午 12:00**，随 EST/EDT 切换。

| 通知 | 含义及处理方式 |
| --- | --- |
| Auto Quant 服务启动 / 运行中 | 进程正在运行，Gateway 和信号就绪状态会单独检查。 |
| IBKR Gateway 中断 | API 无法使用。检查 Gateway，必要时在 IBKR Mobile 批准登录，并在 IBKR 查看持仓。 |
| Gateway 正在重连 | 仍在等待完整的持仓、未完成订单及成交快照。仅建立连接并不足以确认恢复。 |
| Gateway 需要处理 | 账户对账或安全检查未通过，请查看本地停止原因。 |
| 行情不可用 / 被拒绝 / 延迟 | 行情服务器或订阅请求失败、权限或并发登录影响报价，或只能获得延迟/冻结数据。 |
| 行情订阅尚未确认 | 仍在等待报价确认；休市时也可能如此，不会将其标记为已确认的故障。 |
| IBKR Gateway 已恢复 | 对账通过，每项监控订阅都已收到实时数据类型回调和有效买价、卖价或最新成交价。 |
| Gateway API 就绪，但未选择合约 | API 已完成对账，但当前没有要监控的合约，不表示行情已经就绪。 |
| 信号流不可用 / 已恢复 | 已验证心跳停止或执行器落后；恢复需要收到心跳并追上其中声明的信号序号。 |
| Auto Quant 安全暂停 / 已解除 | 需要检查安全暂停，或已通过主动恢复操作解除；Gateway 恢复不会自动解除安全暂停。 |
| 执行循环异常 / 已恢复 | 订单管理发生异常，或已重新成功完成循环；请查看日志和实际持仓。 |
| Auto Quant 服务停止 | 订单管理停止，但不会平仓或取消券商订单。 |
| Auto Quant 失去联系 / 恢复联系 | 中继收不到服务心跳，或重新收到心跳；无法判断具体是虚拟机、进程还是网络故障。 |

状态变化会去重，重启后仍保留去重记录。API 中断和安全暂停会及时报告；Gateway 就绪和行情错误需持续五秒，对账或等待报价提示需持续 30 秒。状态不变时不会反复发送私信，但通知本身仍可能延迟。

行情监控是只读的，仅为当前选择或持有的合约请求流式订阅，遵循已有 IBKR 行情权限，不会购买订阅，也不会请求付费监管快照。API 重连或行情服务器报告恢复后，需要重新确认订阅。IBKR 正常的“闲置、按需可用”消息不会被视为故障。仅仅没有新报价不会触发故障警报，因此无法识别所有静默行情冻结。此监控不改变根据信号定价的交易规则，也不会因通知未送达而阻止保护性订单。

执行循环有响应时，服务约每 **30 秒**向中继发送一次心跳。**连续三分钟收不到心跳**后，中继会排队发送一条失联私信；恢复联系时再发送一条。如果执行循环卡住，60 秒后将停止续发心跳，因此提醒可能约四分钟后才出现。正常停止会通知中继取消监控，不会随后误报心跳丢失。强制终止进程、虚拟机失联或断网无法发送最后一条消息；已开始监控后，这些情况由中继超时检测覆盖。旧版安装需升级后才有心跳监控。

Gateway 健康状态在执行器运行期间检测。主动停止执行器后，不会留下独立的本地 Gateway 监控进程。如果中继、Discord 或机器人自身不可用，同一条通知链路无法及时报告自己的故障。请通过 IBKR 和虚拟机日志核实实际情况。

恢复消息示例（标注 PAPER/LIVE）：

```text
IBKR Gateway recovered: API reconciliation complete and live market-data subscriptions confirmed for the monitored contracts.
PAPER · MNQ
```

## 服务器所有者：创建设置频道

使用 Discord 桌面版或浏览器版，为所有跟随者创建一次此频道即可：

1. 打开 **Auto Quant**，点击左上角的服务器名称，选择 **Create Channel（创建频道）**，也可以点击频道分类旁的 **+**。
2. 选择 **Text（文字频道）**，名称填写 `bot-setup`，不要在前面加 `#`。保持 **Private Channel（私密频道）** 关闭，点击 **Create Channel（创建频道）**。
3. 点击频道旁的齿轮图标 → **Permissions（权限）**。在 **Advanced permissions（高级权限）** 中选择 **@everyone**，用绿色勾选启用 **View Channel（查看频道）**、**Send Messages（发送消息）**、**Read Message History（读取消息历史）** 和 **Use Application Commands（使用应用程序命令）**，然后点击 **Save Changes（保存更改）**。
4. 在同一权限面板中，添加或选择 **AQ Bot** 成员或角色，允许 **View Channel（查看频道）** 和 **Send Messages（发送消息）**，然后保存。
5. 打开 `#bot-setup`，输入 `/link`。命令选择列表中应显示 **AQ Bot**。每位跟随者都应填写自己 Ubuntu 终端显示的配对码。

如果跟随者看不到该命令，请打开 **Server Settings（服务器设置）→ Integrations（集成）→ AQ Bot**，检查跟随者的角色及 `#bot-setup` 是否允许使用 `/link`。可参阅 Discord 官方的[频道权限说明](https://support.discord.com/hc/en-us/articles/10543994968087-Channel-Permissions-Settings-101)和[应用命令权限说明](https://support-apps.discord.com/hc/en-us/articles/26501869403159-Command-Permissions)。

命令回复仅调用命令的跟随者本人可见。测试消息、交易通知和服务通知均通过私信发送。`#bot-setup` 是推荐的频道名称；服务也接受在 Auto Quant 服务器内其他具有相应权限的频道中调用 `/link`。

## 隐私与消息投递

启用此功能后，品种、持仓方向、数量、入场/平仓价、毛盈亏、订单标识符、服务/Gateway 状态和时间会发送给 Auto Quant 的通知服务及 Discord。服务心跳还会告知跟随者是否可连接。消息中不包含 IBKR 登录凭据、账户 ID、中继访问令牌或策略源代码。中继访问令牌仅用于向你配置的中继服务发起 HTTPS 身份验证请求，不会发送给 Discord。提供方只在自己的服务器上保存共用机器人的令牌。常规中继回执仍使用原有的有限字段。

待发送通知保存在交易日志数据库旁的 `executor.notifications.sqlite3` 中。HTTP 投递在交易循环之外运行。服务会按事件 ID 去重，并在遇到网络错误或 Discord 请求频率限制时重试。重复的券商快照通常不会产生重复私信。但如果 Discord 请求长时间超时且发送结果不明确，或进程崩溃，仍可能出现重复私信：Discord 对 `nonce` 的去重只覆盖有限的时间窗口。服务中断或私信被屏蔽可能导致投递延迟；通知不能替代券商账户报表。如果通知存储失败，程序会记录错误并继续交易。请检查本地和服务器日志，排查尚未解决的投递错误。

如需解除关联，请等待空仓，停止服务，然后运行：

```bash
./follow stop
./follow discord unlink
```

解除关联时，通知服务必须可访问。该操作会取消服务器端属于此订阅的待发送通知及心跳监控。重新关联会建立新的收件人绑定，因此，旧队列中的事件不会发送到新关联的 Discord 账号。解除关联后再次启动执行器，交易将继续运行，但不会发送 Discord 通知。
