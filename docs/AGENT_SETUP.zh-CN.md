# 面向客户安装的 AI 助手操作指南

[English](AGENT_SETUP.md) | 简体中文

本指南用于帮助客户安装**分发的字节码安装包**。命令以[安装指南](SETUP.zh-CN.md)为准，客户提示词见[从这里开始](../START_HERE.zh-CN.md)。使用客户的语言沟通。无需克隆源码、反编译、安装开发工具或修改代码。本指南不授权操作提供方的中继或通知服务器。

## 确定起点

如果 `RELEASE.json` 包含 `executor_image`，这是组合容器安装包。请使用
[零基础指南](SETUP.zh-CN.md)、[容器参考](CONTAINER_SETUP.zh-CN.md)及 `./follow-stack setup`，不执行原生安装步骤，
也不安装主机 venv 或 Java。私密提示交给客户自己的终端；setup 可继续中断的步骤，
不会启动交易，`start` 需要客户明确确认模式和手数。

先简短询问：沟通语言、个人电脑操作系统、是否已有 OCI 虚拟机及 SSH 连接，以及是新安装、继续中断的安装还是升级。找到压缩包、校验文件和解压目录。明确每条命令是在**客户自己的电脑**、**通过 SSH 连接的 Ubuntu**，还是 **VNC 远程桌面**执行。使用 `RELEASE.json` 中的版本和实际收到的文件名。

如果没有终端或 SSH 访问能力，应明确说明，并每次只给客户一个操作。不得声称执行过自己无法访问的命令或点击过界面。未经客户要求，不代其安装或登录 AI 工具；需要时参考工具官方说明。

修改已有虚拟机前，使用 `systemctl --user is-active follow-executor.service follow-gateway.service` 检查执行器和 Gateway 的状态。首次安装时服务未运行或不存在可能是正常的，应与 SSH 或用户会话失败区分。通过 `systemctl --user show` 查看现有单元的 `WorkingDirectory` 和 `ExecStart`，确定当前安装版本。换了一个版本目录，不代表没有旧配置。

如果交易正在运行，不要停止、重装、重新配置或启动第二个执行器。先查看状态，并请客户检查 IBKR。只有确认没有持仓及未完成订单、且客户准备好停止后，才按[更新流程](SETUP.zh-CN.md#update)操作。仅凭本地日志数据库或尚未收全的空券商缓存，不能证明账户已空仓。

## 提问、私密输入和决策

只询问当前阶段需要的信息，解释原因并提供指南中的默认值。品种和数量由客户选择，不要推定其同意某个交易数量。新安装先用模拟模式。除非客户明确要求按对应流程变更，否则保留已有账户身份、模式、数量和时间计划。

| 信息 | 获取方式 |
| --- | --- |
| 虚拟机 IP、SSH 用户名、私钥文件位置 | 已知则不重复询问；使用私钥文件，但不显示内容。 |
| 提供方指纹 | 询问预期的非秘密指纹，并在检查中与 `leader_key_id` 比较。不能仅从同一安装包推导出指纹，就当作独立核验成功。 |
| 品种、数量、Discord 选项、周日时间 | 在对话中询问，配置前确认。 |
| IBKR 账户 ID | 由客户在配置向导输入，并与 Gateway 核对；避免复制到聊天或进度记录。 |
| IBKR 用户名/密码、relay token、VNC 或 sudo 密码 | 客户在自己的终端或官方登录界面直接输入。不要在聊天中索取，也不要放进命令参数或环境变量。 |
| Discord 一次性关联码 | 客户在自己的终端运行关联命令，将显示的码提交给 AQ Bot 的 `/link`；不要保存该码。 |

当 `./scripts/gateway-desktop.sh`、`./follow gateway configure` 或 `./follow configure` 需要私密输入时，让客户在**自己的交互式 SSH 终端中，进入安装目录后**运行命令。不要在客户无法输入的助手专用终端里启动隐藏密码提示。先解释非秘密选项，等客户完成后再用状态或检查命令验证。不要让秘密资料经过模型来驱动交互提示。如果隐藏输入不可用，或出现可能回显输入的警告，应取消并使用真正的交互式终端。

不得读取、显示、上传或将 `relay.token`、`ibc.ini`、SSH 私钥、VNC 密码文件及其备份内容放入工具输出。不要转储整份配置、主目录、环境变量或日志。程序运行时必然会读取自己的凭据；这里限制的是将凭据暴露给助手或会话记录。拥有虚拟机权限在技术上可能允许读取这些文件；本指南是行为说明，并非隔离机制。使用公开的状态命令和限定长度的诊断输出，共享前遮盖账户或交易详情，备份保持私密。

客户已要求安装时，可继续常规安装。账户验证、接受条款、手机批准和 Discord 同意及关联由客户完成。创建付费资源前，确认具体费用。**首次启动交易前**，总结已核实的账户模式、品种及数量，取得客户针对这套设置的明确同意。不要代填 `LIVE` 确认。切换实盘和 `./follow resume` 需要各自明确的决定；`resume` 可能接管或关闭券商持仓。

组合包的服务检查使用已安装版本中的 `./follow-stack service-status` 和
`./follow-stack gateway status`。只检查旧的 `follow-executor.service` 无法识别容器执行器。
完整执行 SETUP 的五步向导、行情就绪和明确启动流程，不套用下方原生检查点表。
后续容器状态、检查及 Discord 命令使用 `follow-stack`，不要运行原生 `follow configure`。

## 仅适用于原生安装包的检查点

如果客户已选择容器试用，或 `gateway status` 显示 `backend: docker`，先阅读
[GATEWAY_DOCKER.zh-CN.md](GATEWAY_DOCKER.zh-CN.md)，用其中流程替代检查点 3–5。
不要运行原生桌面脚本或询问安装目录。将 `./follow gateway configure --backend docker --vnc`
的私密输入交给客户。首次安装 Docker 后需重启虚拟机一次以刷新服务组权限，先保存进度。
继续时保留已选后端，不迁移活动安装，仍执行相同的就绪检查和交易启动检查点。
Docker 卷也包含凭据，不要读取卷内容或把 Docker inspect 原始输出贴到聊天；使用不含秘密的 `gateway status`。

每个阶段先阅读链接对应的安装章节。有依赖的命令按顺序执行，检查退出状态和实际结果后再继续。使用随包脚本，不临时重写替代方案。不要运行 `sudo ./install.sh` 或 `sudo ./follow`；脚本会自行请求所需权限。

| 阶段 | 操作与通过依据 |
| --- | --- |
| 1. 账户与虚拟机 | 按[准备](SETUP_NATIVE.zh-CN.md#prepare)和 [OCI 图文指南](OCI_ARM.zh-CN.md)操作。客户完成注册并确认区域、容量和费用。验证 SSH 可用、Ubuntu 为 24.04、架构为 `aarch64`、Python 为 3.12。不要在个人电脑上运行 Linux 安装器。 |
| 2. 验证并安装 | 按[传输](SETUP_NATIVE.zh-CN.md#transfer)和[安装](SETUP_NATIVE.zh-CN.md#install)操作。使用可信的配套校验文件验证原始压缩包，在 Ubuntu 的全新固定目录解压，运行 `./install.sh --verify-only`，再运行 `./install.sh`。必须看到验证及安装成功；交易仍保持停止。 |
| 3. 桌面与 Gateway | 按 [Gateway 设置](SETUP_NATIVE.zh-CN.md#gateway)操作，将 VNC 密码输入交给客户。客户通过 SSH 隧道访问仅监听本机的桌面，安装固定版本 Gateway、审阅条款，并关闭手动打开的 Gateway。不要向公网开放 5901、4001 或 4002。 |
| 4. Gateway 配置 | 让客户运行 `./follow gateway configure`。新安装默认：paper、`America/New_York`、每日 `23:45`、周日 `12:00`。这是随 EST/EDT 切换的美国东部时间，不是固定 UTC−5。保留已有计划；允许的修改见 [IBC 指南](IBC.zh-CN.md)。 |
| 5. Gateway 登录 | 运行 `./follow gateway start`；客户在 IBKR Mobile 批准，并在 VNC 检查首次登录。查看 `./follow gateway status`。进程运行不能证明登录成功。请在对应点击操作前，展示 [API 设置步骤](SETUP_NATIVE.zh-CN.md#gateway-api)中的两张截图。客户核对模拟账户、API 端口 4002、Read-Only API 已关闭、仅本机连接，并处理提示框。 |
| 6. 跟单设置 | 按[配置](SETUP_NATIVE.zh-CN.md#follower)让客户运行 `./follow configure`，私密输入账户 ID 和 relay token。确认 paper 模式、品种及数量。对已有配置重跑此向导只会修改品种/数量，不能当作继续安装或检查命令。 |
| 7. 可选 AQ Bot | 按 [Discord 设置](SETUP_NATIVE.zh-CN.md#discord)解释会共享交易详情、服务/Gateway 状态及心跳。在客户提交 `/link` 前，展示随包提供的 #bot-setup 截图。客户运行 `./follow discord link` 并同意，使用自己的 Discord 账户，在 Auto Quant → #bot-setup → AQ Bot → `/link` 关联。确认收到测试私信，执行器停止时运行 `./follow discord status` 和 `./follow discord enable`。客户无需创建机器人或 bot token。 |
| 8. 准备状态 | 执行器停止时运行 `./follow check`。必须退出码为 0、`problems: []`、`account_type`、`root`、`quantity` 正确，且 `leader_key_id` 已独立核验。客户在 Gateway 核对账户 ID。此检查可能请求 what-if 保证金估算，但不会提交可成交的订单。使用 `--skip-broker` 不足以通过此检查点。 |
| 9. 启动交易 | 展示结果、未解决事项及准确的 paper 模式、品种和数量。说明 `./follow start` 可能立即提交符合条件的订单，并启用开机自启。客户明确同意后运行一次，再检查服务状态及限定长度的日志。若客户不启动，以**已配置，交易停止**结束。 |

限定长度的进程诊断可用 `systemctl --user --no-pager status follow-executor.service` 或 `journalctl --user -u follow-executor.service -n 60 --no-pager`（各为一行）。Gateway 日志使用 `follow-gateway.service`。不要在助手工具里使用持续运行的 `./follow logs`、`./follow gateway logs` 或 `./follow watch`。客户查看日志时，Ctrl+C 仅退出查看器，不要用停止服务的命令退出查看器。

`./follow check` 不能证明所有实时行情订阅已就绪。获准启动后，AQ Bot 的完整 Gateway 就绪/恢复消息要求 API 对账完成并确认实时行情。仅 API 就绪或等待行情是不同状态，休市时行情可能无法确认。区分**已安装**、**已配置**、**检查通过**、**正在运行**和**已观察到模拟交易**。不要只为了通过检查而提交测试订单；没有证据时，不得声称已测试成交、止损、每周重新认证或恢复。

## 在设置时展示 Gateway 界面说明

到第 5 阶段时，主动为客户打开 [Gateway API 设置章节](SETUP_NATIVE.zh-CN.md#gateway-api)。按顺序逐张展示安装包中的两张截图，先展示图片，再说明对应点击位置：

1. `docs/images/ib-gateway-configure-menu.png`：**Configure → Settings**。
2. `docs/images/ib-gateway-api-settings.png`：**API → Settings**。

每次只给一个操作，解释 Read-Only API 应不勾选，模拟账户的 Socket port 应为 4002。Gateway 自动启用 API 连接，缺少 ActiveX 勾选框是正常情况。

工具支持时，使用客户可见的图片或文件预览。在聊天中嵌入本地图片时，根据实际解压目录确定图片的绝对路径。仅用模型查看工具读取图片，不代表客户已经看到了图片。界面不能显示图片时，提供可点击的文件链接，或引导客户打开自己电脑上已解压安装包中的指南。不要保证所有 AI 工具都会弹出图片，也不要在无图形界面的虚拟机启动查看器后，就认为图片出现在客户电脑上。缺少图片时应明确说明，并使用文字步骤；不得编造截图或声称已展示。

参考截图不能证明客户自己的设置正确。请客户在 VNC 桌面中核对设置，并点击 Apply/OK 保存后，再标记此检查点完成。之后仍须进行正常的准备状态检查。

## 展示 Discord 关联界面

到第 7 阶段时，如果客户需要通知，请在其提交 AQ Bot 的 `/link` 命令前，展示 `docs/images/discord-bot-setup-link.png`。沿用上文的客户可见预览或文件链接方式，指出 **#bot-setup**、**/link** 命令及 **code** 输入框。解释 `xxxxxxx` 是占位示例，必须换成客户自己的 Ubuntu 终端刚显示的关联码；不需要点击管理员的 **Edit Channel** 按钮。客户直接在 Discord 中填写关联码，不要让其发到助手聊天中，也不要保存在进度记录中。收到私密关联确认和测试私信后，才能标记投递已验证。

## 继续安装，不重置状态

在 Ubuntu 的 `~/.local/state/auto-quant-onboarding/progress.md` 保存简短进度记录，放在受校验的安装目录及应用状态目录之外。新建其父目录时使用 `0700`，文件使用 `0600`；不要修改无关目录的权限。每完成一个阶段或把操作交给客户时更新。如果尚未连接 Ubuntu，先在聊天中提供不含秘密的进度摘要，连接后再保存。已有记录应先阅读，再更新。

只记录：版本及安装路径、最后验证的阶段和时间、paper/live 模式、品种及数量、计划时间、Discord 已启用/跳过/待处理、是否已获准及执行交易启动、下一步，以及清理过敏感信息的错误摘要。不记录密码、用户名、账户 ID、token、关联码、私钥内容、原始配置/日志或交易/信号数据。准确记录客户决定；旧记录不构成对另一账户、数量或模式的授权。

继续时先读记录，再重新核对服务状态和已完成的检查点。过时记录不能成为重装、停止运行中服务，或重复启动/同意操作的理由。已有 Gateway 配置时使用 `./follow gateway status`；用 `./follow status` 查看本地日志状态，仅在执行器停止时运行 `./follow check`。存在某个文件不代表成功。不要删除日志数据库、通知队列或凭据来伪造全新安装；不要把活动状态复制给第二个执行器。升级按[更新流程](SETUP_NATIVE.zh-CN.md#update)，保留私密配置及状态。

## 检查点失败时

| 问题 | 下一步 |
| --- | --- |
| 校验失败、不支持的系统/Python/CPU、上游固定下载校验不符 | 停止当前阶段，重新核对原始可信文件和平台。必要时向 Auto Quant 获取兼容版本；不要关闭验证、更改固定哈希或安装任意供应商版本。 |
| SSH 失败或 OCI 无 A1 容量 | 按 [OCI 故障排查](OCI_ARM.zh-CN.md#oci-help)核对 IP、密钥路径和网络。区域及付费资源由客户决定。不要开放所有端口或削弱 SSH 验证。 |
| VNC/Gateway 登录/API 不可用 | 检查私密 SSH 隧道、服务状态及限定长度日志。客户检查 Gateway 并批准手机。不要强制踢掉另一个 IBKR 会话，或反复重启正在交易的系统。 |
| 账户错误、安全暂停、持仓/订单或保证金检查失败 | 保留状态，说明具体失败，按[运维指南](OPERATIONS.zh-CN.md)处理。客户检查 IBKR。不要用提高限额、关闭检查、撤单、平仓或执行恢复来绕过安装问题。 |
| 中继未授权或指纹不匹配 | 请 Auto Quant 核对订阅或预期指纹；不要打印 token 或为了匹配而替换验证公钥。 |
| Discord 关联码过期、命令缺失或私信被阻止 | 按 [Discord 指南](DISCORD.zh-CN.md)处理。客户可获取新码、检查频道权限并允许私信。如果选择暂不启用通知，记录待处理/已跳过；未收到私信不能标记投递已验证。 |
| 助手无法完成界面或私密输入 | 告诉客户准确位置、一个操作及预期结果，等待完成后再做依赖此步骤的工作。 |

结束时用简明语言交接：已安装和正在运行的内容、已确认的模式/品种/数量及每周计划、Discord 状态、剩余检查、进度记录位置，以及客户下一步。说明 `./follow stop` 会停止管理及开机自启，但不会平仓或撤单。未来实盘部署前，仍需观察实际模拟账户登录、成交/止损和重连行为。

入口文件参考：[Codex AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md) 和 [Claude Code 项目说明](https://code.claude.com/docs/en/memory)。
