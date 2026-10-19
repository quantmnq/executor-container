# IBC：定时 Gateway 登录与手机批准

[English](IBC.md) | 简体中文

本页介绍原生后端。[可选容器试用方案](GATEWAY_DOCKER.zh-CN.md)使用相同的私密 IBC 配置和时间计划，
通过固定摘要的上游镜像运行；其安装、恢复画面、数据存储和升级方式请参阅对应指南。

客户安装器从上游下载 **IBC 3.24.2** 并校验 SHA-256。桌面辅助脚本下载固定版本的原生 **IB Gateway 10.51 ARM64** 安装器，其中包含 **Java 25**。IBC 是独立的第三方组件。安装它不会启动 Gateway 或交易。

## 1. 安装私有桌面和 Gateway

按[完整安装指南](SETUP.zh-CN.md)的步骤 1–5 操作。在 VNC 内运行 Gateway 安装器，接受 IBKR 条款，并记下安装目录。使用 Ubuntu 登录用户拥有的目录，通常为 `~/Jts/ibgateway/1051`。如果安装器启动了 Gateway，请先关闭其窗口，再启动 IBC。保持 VNC 桌面运行。

IBC 使用单独的持久 Gateway 设置目录，不导入之前手动启动 Gateway 时的设置。首次通过 IBC 登录时，仍需在 VNC 内检查 API 设置、条款和账户特有的对话框。使用 IB API 模式。

## 2. 首次配置 IBC

在安装目录中，确认执行器和 Gateway 均已停止，然后运行：

```bash
./follow gateway configure
```

向导会询问：

| 设置 | 含义 |
| --- | --- |
| Gateway installation directory | 包含 `jars` 和 `ibgateway.vmoptions` 的目录 |
| Account mode | 初期选择 `paper`；如果执行器已有配置，会沿用其模式和端口 |
| Schedule timezone | 默认 `America/New_York`；其他 IANA 时区名称包括 `UTC`、`America/Los_Angeles` 或 `Asia/Shanghai` |
| Daily automatic restart | 活跃交易时段之外的每日重启时间，24 小时制 `HH:MM`，默认 `23:45` |
| Sunday mobile approval time | 周日方便批准手机请求的时间，24 小时制 `HH:MM`，默认 `12:00` |
| IBKR login username/password | 终端隐藏输入；使用所选账户模式对应的登录凭据 |

默认计划时区为 `America/New_York`：周日手机批准时间为**美国东部时间中午 12:00**，每日重启时间为**美国东部时间 23:45**。冬季使用 EST，夏季使用 EDT，不会修改虚拟机的系统时区。重新配置时会保留之前保存的计划。两个时间都使用所选时区，并遵循其夏令时规则。向导会检查未来两年内的周日，确保预约时间晚于 IBKR **美国东部时间周日 01:00** 的令牌失效时间，并留出 15 分钟余量。例如，`12:00 UTC` 有效，而亚洲时区的周日上午可能太早。夏令时切换时存在歧义或不存在的周日时间会被拒绝。每日重启和周日登录不能设为同一时间。请选择允许短暂断线的时间。

实盘模式需要输入 `LIVE` 确认。每位客户在自己的虚拟机上输入自己的凭据，不要发送给 Auto Quant 或 Discord。凭据保存在 `~/.config/follow-executor/gateway/ibc.ini`，文件权限为 `0600`，所在目录为 `0700`。Java 属性转义只是编码，不是凭据加密；虚拟机用户及 root 可以读取该文件。凭据不会写入 Shell 历史、服务参数、发布压缩包或中继请求。请保护所在目录及备份。

## 3. 启动 Gateway 并在 IBKR Mobile 批准

```bash
./follow gateway start
./follow gateway logs
```

在 IBKR Mobile 中按正常身份验证流程批准登录通知。IBC 发起登录，并能在错过手机提示后重试，但不能代替你批准双重认证。此流程要求使用 **IB Key / IBKR Mobile 推送认证**。要求通行密钥、密码卡或其他交互式认证的账户可能仍需 VNC，不支持仅靠手机批准的完整流程。

首次登录后请在 VNC 中检查：账户模式、API 端口（**模拟盘 4002**、**实盘 4001**；执行器配置自定义端口时除外），以及**仅允许本机连接**。IBC 会设置 API 端口、关闭 Read-Only API，并信任 `127.0.0.1`；它会拒绝意外的 API 连接提示。不要向公网开放 API 或 VNC 端口。其余 IBKR 提示请自行处理。如果出现自动重启确认，请点击一次 **OK**，让首次配置完成。如果已有其他交易会话，本配置不会强制将其踢下线；请先主动关闭该会话，再在执行器停止时重启这里的 Gateway。

具体点击位置见 [Gateway API 设置步骤](SETUP.zh-CN.md#gateway-api)。Gateway 会自动启用 API 连接，找不到 “Enable ActiveX and Socket Clients” 勾选框不影响设置。

IBC 会重命名 Gateway 原始启动器，以控制自动重启。配置后请使用 `./follow gateway start`，不要使用旧桌面快捷方式。Ctrl-C 只退出日志查看器，不会停止 Gateway。

登录成功后，继续主指南中的 `./follow configure`、Discord 关联、`./follow check` 和 `./follow start`。Gateway 登录本身不会启动交易。如果执行器配置中选择了不同的模式或端口，请停止 Gateway 并重新配置，使两者一致。

## 4. 每周和每日行为

私有桌面可用后，用户服务会启动 Gateway；虚拟机重启后也会执行。任何需要全新登录的重启都可能触发手机批准请求，请在需要交易之前完成。每日自动重启通常沿用当前会话。周日，IBC 的 `ColdRestartTime` 会在你选定的时间发起完整登录，跟随者在手机上批准。修改预约时间不会改变 IBKR 服务器端的令牌失效安排。IBKR 也可能在其他时间要求验证。

错过提示后，IBC 会在认证尝试超时时重试。不要未经检查就批准意外的登录请求。如需停止重复尝试，请在空仓时安全停止执行器，再停止 Gateway 服务。

| 命令 | 用途 |
| --- | --- |
| `./follow gateway status` | 显示模式、端口、时区、计划和进程状态，不显示凭据 |
| `./follow gateway logs` | 查看 IBC 启动及认证日志 |
| `./follow gateway stop` | 停止 Gateway 并禁用其自启；执行器服务运行时会拒绝 |
| `./follow gateway start` | 启用自启并启动 Gateway |

进程正在运行不代表认证成功。执行器停止时，使用 `./follow check` 确认就绪。Gateway 不可用时，执行器无法提交或修改订单。停止任一服务都不会平仓或取消券商订单。

## 5. 修改计划、凭据及升级

等待空仓且无未完成订单后运行：

```bash
./follow stop
./follow gateway stop
./follow gateway configure
./follow gateway start
```

向导会将已有计划作为默认值，并再次要求输入凭据。批准手机请求后，运行 `./follow check` 和 `./follow start`。不要通过编辑 `ibc.ini` 切换账户或模拟/实盘模式；请按[账户迁移流程](OPERATIONS.zh-CN.md)操作并配置两个组件。

升级安装包时，先停止两个服务并备份私人配置和状态。将新版本安装到新目录。安装器会下载 IBC 并更新 Gateway 服务路径，同时保留凭据、计划和 Gateway 设置。在新目录运行 `./follow gateway start`，批准所需登录请求，再检查并启动执行器。验证完成前保留旧版本。

从 0.1.0 版本的手动 Gateway 设置升级时，旧版本没有 `gateway` 命令。请在空仓时停止执行器并手动关闭 Gateway。安装新包后，完成上述步骤 1–3，安装受支持的 Gateway 版本并首次配置 IBC。

IBC/Gateway 下载均固定了校验和。如果 IBKR 替换下载文件，辅助脚本会因校验不匹配而停止；请向 Auto Quant 获取更新后的安装包。不要绕过校验，也不要擅自换用未经验证的 IBC/Gateway 版本。IBC 上游仓库已于 2026 年 9 月归档；本集成使用其固定版本，未来 Gateway 变更仍需评估兼容性。

本版本的验证涵盖字节码测试，以及在不输入凭据的情况下通过 IBC 打开真实 ARM64 Gateway 登录窗口。实际手机批准、已认证会话的每日/每周重启，以及模拟交易恢复，仍需使用跟随者自己的账户验证后再用于实盘。

参考资料：[IBC 版本](https://github.com/IbcAlpha/IBC/releases/tag/3.24.2)、[IBC 配置](https://github.com/IbcAlpha/IBC/blob/3.24.2/resources/config.ini)、[IBKR 每周认证](https://www.ibkrguides.com/traderworkstation/auto-restart-considerations.htm)。
