# 从零创建 Oracle 云电脑：新手图文指南

[English](OCI_ARM.md) | 简体中文 | [返回安装指南](SETUP.zh-CN.md)

本指南从注册 Oracle 账户开始，带你连接到一台 Ubuntu 云电脑。Oracle 将这台电脑称为 **instance（实例）**或 **virtual machine / VM（虚拟机）**。它运行在 Oracle 的数据中心，因此 Auto Quant 运行时，你自己的电脑不必一直开着。你不需要会编程。

**以下操作从你自己的电脑开始。** 先使用浏览器，之后使用“终端”——一个可以粘贴命令的窗口。本指南中的操作不会启动交易。

下方截图来自 Oracle 和 Ubuntu 的开发公司 Canonical。图片从其官方网站加载，需要联网；点击图片可以放大。这些是官方教程的示例图，不是你的账户截图，名称、日期和界面布局可能不同。请以本指南文字中要求的设置为准。操作说明核对日期：**2026-10-11**。

- [1. 注册 Oracle 账户](#oci-account)
- [2. 创建网络](#oci-network)
- [3. 允许自己的电脑连接](#oci-firewall)
- [4. 创建 Ubuntu 实例并保存密钥](#oci-instance)
- [5. 连接 Ubuntu](#oci-connect)
- [6. 检查是否准备就绪](#oci-check)
- [遇到问题怎么办](#oci-help)

<a id="oci-account"></a>
## 1. 注册 Oracle 账户

**操作位置：你自己电脑的浏览器。** 如果已有 OCI 账户，请在 [Oracle Cloud](https://cloud.oracle.com/) 登录，然后跳到第 2 步。

准备好电子邮箱、手机和付款卡。Oracle 可能要求这些信息来验证身份。请阅读页面显示的费用和条款；Oracle 账户与 Auto Quant 订阅是两回事。免费试用额度并不代表你选择的所有资源都一直免费。详见 [Oracle 免费套餐说明](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier.htm)。

1. 打开 [Oracle 注册页面](https://signup.oraclecloud.com/)。
2. 填写国家、姓名和邮箱，完成人机验证，然后点击 **Verify my email（验证邮箱）**。
3. 打开 Oracle 发来的邮件，点击验证链接。

[![Oracle 注册表单：国家、姓名、邮箱及人机验证](https://docs.oracle.com/en/learn/get-started-with-oci-and-oci-console/images/Getting-Started-OCI4.png)](https://docs.oracle.com/en/learn/get-started-with-oci-and-oci-console/images/Getting-Started-OCI4.png)

*截图来源：Oracle [账户注册教程](https://docs.oracle.com/en/learn/get-started-with-oci-and-oci-console/)。请填写你自己的信息。*

4. 设置密码。记下 **Cloud Account Name（云账户名称）**，之后登录 Oracle 时会用到。
5. 选择 **Home Region（主区域）**，也就是这次部署所在的地理区域。请仔细选择：Oracle 说明，注册后不能更改主区域。Always Free 云主机必须建在主区域，是否有空余容量仍以实际情况为准。
6. 按 Oracle 的提示完成地址、手机和付款验证，阅读协议后提交注册。
7. 等待账户开通邮件。打开 [Oracle Cloud](https://cloud.oracle.com/)，输入云账户名称，完成登录及 Oracle 要求的安全验证。[Oracle 注册说明](https://docs.oracle.com/en-us/iaas/Content/GSG/Tasks/signingup_topic-Sign_Up_for_Free_Oracle_Cloud_Promotion.htm)

[![Oracle 账户设置：云账户名称与主区域](https://docs.oracle.com/en/learn/get-started-with-oci-and-oci-console/images/Getting-Started-OCI11.png)](https://docs.oracle.com/en/learn/get-started-with-oci-and-oci-console/images/Getting-Started-OCI11.png)

*截图来源：Oracle [注册教程](https://docs.oracle.com/en/learn/get-started-with-oci-and-oci-console/)。图中的荷兰仅为示例，不是要求你选择的区域。*

**完成标志：** 你能看到 Oracle Cloud Console（云控制台），即管理云电脑的网站。保持页面顶部选中你刚才选择的主区域。

<a id="oci-network"></a>
## 2. 为 Auto Quant 创建网络

**操作位置：浏览器中的 Oracle 云控制台。** **VCN** 是云电脑使用的网络；**compartment（区间）**可以理解为存放 Oracle 资源的文件夹。对于新注册的个人账户，本指南统一使用账户的 **root（根区间）**。

1. 打开左上角菜单 **☰ → Networking（网络）→ Virtual cloud networks（虚拟云网络）**。
2. 点击 **Start VCN Wizard（启动 VCN 向导）**。某些界面将它放在 **Actions（操作）**里。
3. 选择 **VCN with Internet Connectivity（具有互联网连接的 VCN）**，然后启动向导。

[![Oracle VCN 向导中的互联网连接选项](https://docs.oracle.com/en/applications/peoplesoft/cloud-manager/tutorial-create-vcn-console/images/create_vcn_wizard_start.png)](https://docs.oracle.com/en/applications/peoplesoft/cloud-manager/tutorial-create-vcn-console/images/create_vcn_wizard_start.png)

*截图来源：Oracle [VCN 教程](https://docs.oracle.com/en/applications/peoplesoft/cloud-manager/tutorial-create-vcn-console/index.html)。这里只使用其中创建网络的部分。*

4. 将网络命名为 **auto-quant-network**，选择相同的根区间。
5. 保留向导建议的网络地址范围和 DNS 设置。本指南不启用 IPv6，你不需要自行计算网络地址。
6. 检查将创建的资源及页面显示的费用，然后点击 **Create（创建）**。
7. 完成后点击 **View Virtual Cloud Network（查看虚拟云网络）**。找到名称含 **public（公共）** 的子网，第 4 步创建实例时会使用它。

向导会配置通往互联网的连接。只有私有子网时，无法按下面的方式从自己的电脑直接连接。[Oracle 当前网络向导说明](https://docs.oracle.com/en-us/iaas/Content/Network/Tasks/quickstartnetworking.htm)

**完成标志：** 网络已创建，而且你能打开它的公共子网。

<a id="oci-firewall"></a>
## 3. 只允许自己的电脑连接

**操作位置：浏览器。** **Security list（安全列表）**规定哪些连接可以进入。用来控制 Ubuntu 的 SSH 连接使用 **22 端口**。

1. 在另一个浏览器标签页搜索 **what is my IPv4 address**，复制由四组数字组成的结果。这是你家里或办公室的公网地址，不是即将创建的云电脑地址。
2. 返回 **auto-quant-network → Subnets（子网）→ 公共子网 → Security Lists（安全列表）**，打开其安全列表，找到 **Ingress Rules（入站规则）**。
3. 如果已有允许 TCP 目标端口 **22** 的规则，请编辑它；否则按下表添加。不要同时保留一条允许所有人访问 22 端口的规则，因为范围小的新规则不会覆盖范围大的旧规则。

| 字段 | 填写内容 |
| --- | --- |
| Stateless | 不勾选 |
| Source Type | CIDR |
| Source CIDR | 家里或办公室的公网 IPv4 地址，后面加 `/32` |
| IP Protocol | TCP |
| Source Port Range | All；如果表单用空白代表 All，就留空 |
| Destination Port Range | `22` |
| Description | My computer SSH |

例如，如果你的地址是 `203.0.113.10`，就填写 `203.0.113.10/32`。**这只是示例，请使用你自己的地址。** `/32` 表示只允许这一个地址，`0.0.0.0/0` 表示所有人。

保留已有的 ICMP 网络规则和默认 **Egress（出站）**规则。不要添加开放 **4001、4002 或 5901** 的入站规则，也不要添加“允许所有连接”的入站规则。Gateway 和远程桌面将使用私密连接。

这里创建的是 Auto Quant 专用的新网络。如果你要复用一个共享网络，请先让其管理员检查所有关联的安全列表及网络安全组，再修改规则。[Oracle 安全列表的工作方式](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/securitylists.htm)

**完成标志：** 只有你当前的公网地址可以通过 SSH 连接。以后更换 Wi-Fi、开启 VPN 或运营商更换公网地址时，请先更新这条规则，再尝试重新连接。保留 Ubuntu 自身的防火墙。

<a id="oci-instance"></a>
## 4. 创建 Ubuntu 实例

**操作位置：浏览器中的 Oracle 云控制台。**

打开 **☰ → Compute（计算）→ Instances（实例）→ Create instance（创建实例）**。表单可能是一整页，也可能分为多个带 **Next（下一步）**按钮的页面。在点击最后的 **Create** 之前，完成下面各项。[Oracle 实例创建说明](https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/launchinginstance.htm)

[![Oracle 实例列表中的 Create Instance 按钮](https://docs.oracle.com/en/learn/oci-basics-tutorial/img/014.png)](https://docs.oracle.com/en/learn/oci-basics-tutorial/img/014.png)

*截图来源：Oracle [OCI 基础教程](https://docs.oracle.com/en/learn/oci-basics-tutorial/)。你的实例列表会与示例不同。*

### 名称、系统镜像和机型

**Image（镜像）**是要安装的操作系统；**Shape（机型）**是云电脑的类型和配置。这个 Auto Quant 安装包需要以下设置：

| 设置 | 选择 |
| --- | --- |
| Name | `auto-quant` |
| Compartment | 与网络相同的根区间 |
| Placement | 当前区域内有空余容量的可用域；其他选项保持默认 |
| Capacity type | On-demand（按需），不要选择 preemptible（可抢占） |
| Image | **Canonical Ubuntu 24.04 LTS**，**ARM64 / aarch64** |
| Shape | **Ampere → VM.Standard.A1.Flex** |
| OCPUs | **2** |
| Memory | **8 GB** |

在 **Image and shape** 中点击 **Change image → Ubuntu**，选择 24.04 的 ARM64/aarch64 版本。如果同时提供完整版本和 Minimal（精简版），优先选择完整版本。通过 **Change shape** 选择 Ampere A1，然后重新检查镜像和机型：某些镜像选项会改变可用机型。即使示例截图显示其他版本，这个安装包也必须使用 Ubuntu 24.04 和 ARM64。[Canonical 的 Ubuntu 镜像选择说明](https://ubuntu.com/docs/oracle/oracle-how-to/find-ubuntu-images/)

[![Canonical 提供的 OCI Ubuntu 镜像选择面板截图](https://ubuntu.com/docs/oracle/_images/1_latest_ubuntu_image.png)](https://ubuntu.com/docs/oracle/_images/1_latest_ubuntu_image.png)

*截图来源：Canonical [镜像指南](https://ubuntu.com/docs/oracle/oracle-how-to/find-ubuntu-images/)。无论示例选中了哪个版本，Auto Quant 都要选择 **24.04 ARM64/aarch64**。*

2 个 OCPU 和 8 GB 内存是运行 Gateway 及桌面的起步配置，并非经过验证的最低要求，也不代表一定免费。请核对你的可用额度、已有资源和费用估算。如果 A1 容量不足，可尝试当前区域提供的另一个可用域，或稍后再试。AMD/Intel 实例不能代替这个 ARM64 安装包所需的机型。

### 网络和 SSH 密钥

| 设置 | 选择 |
| --- | --- |
| Virtual cloud network | `auto-quant-network` |
| Subnet | 第 2 步创建的 **public（公共）**子网 |
| Assign a public IPv4 address | **Yes / 启用** |
| Network security groups | 本专用网络操作流程中保持不选 |
| Add SSH keys | **Generate a key pair for me（为我生成密钥对）** |

**SSH 密钥**是一份小文件，用于解锁对 Ubuntu 云电脑的访问。离开页面前，点击 **Download private key（下载私钥）**和 **Download public key（下载公钥）**。旧版界面的按钮叫 **Save Private Key** 和 **Save Public Key**。

[![Oracle SSH 密钥区域中的私钥及公钥保存按钮](https://docs.oracle.com/en/learn/oci-basics-tutorial/img/021.png)](https://docs.oracle.com/en/learn/oci-basics-tutorial/img/021.png)

*截图来源：Oracle [OCI 基础教程](https://docs.oracle.com/en/learn/oci-basics-tutorial/)。连接时使用的是私钥。*

在**你自己的电脑**上找到刚下载的**私钥**（不是 `.pub` 文件），将它重命名为 **auto-quant.key**。本指南将它放在 **Downloads（下载）**文件夹；请另做一份私密备份。不要发送给 Auto Quant、Discord 或其他人。Windows 用户请开启文件扩展名显示，避免误改成 `auto-quant.key.key` 或 `auto-quant.key.txt`。

### 磁盘与最终确认

保留标准启动磁盘大小、性能和其他设置，本流程不需要额外磁盘。查看费用估算。在点击 **Create** 前，确认是 **Ubuntu 24.04**、**A1 ARM64**、**2 个 OCPU / 8 GB 内存**、**公共子网和公网 IPv4**，并且私钥已经保存。

点击 **Create**，等待实例状态变成 **Running（运行中）**。在实例详情中复制 **Public IPv4 address（公网 IPv4 地址）**；它有时位于 **Networking** 或主网络接口下。不要复制私网地址，也不要复制 OCID——那是一串很长的资源标识符。[Oracle 首台实例教程](https://docs.oracle.com/en-us/iaas/Content/Compute/tutorials/first-linux-instance/overview.htm)

**完成标志：** 实例显示 Running，你也已经拿到公网 IPv4 地址，且私钥文件保存在自己的电脑上。

<a id="oci-connect"></a>
## 5. 第一次连接 Ubuntu

**操作位置：你自己电脑上的终端。**

- **Windows 10/11：** 打开“开始”，搜索 **PowerShell** 并打开。
- **Mac：** 按 **Command + 空格**，搜索 **Terminal（终端）**，按回车打开。
- **Linux：** 打开终端应用。

每次粘贴一行，按回车执行。先进入下载文件夹：

```bash
cd ~/Downloads
```

如果你使用了其他下载文件夹，请在那个文件夹里打开终端。该文件夹中必须有 **auto-quant.key**。Mac/Linux 用户还需要运行下一行，让私钥只能由自己读取。**Windows PowerShell 用户跳过这一行。**

```bash
chmod 400 auto-quant.key
```

现在连接云电脑。**将 `YOUR_OCI_PUBLIC_IP` 替换为第 4 步复制的实例公网 IPv4 地址。** 其他内容，包括 `ubuntu@`，保持不变。

```bash
ssh -i ./auto-quant.key ubuntu@YOUR_OCI_PUBLIC_IP
```

第一次连接会询问是否信任服务器。核对地址是否与你从 OCI 复制的一致；对于这台新实例，输入 `yes` 并按回车。以后如果出现“主机身份已更改”的警告，请先停下来检查原因，不要直接删除警告。SSH 密钥负责登录；如果意外要求输入登录密码，不要填写 Oracle 或 IBKR 密码。[Oracle Linux 连接说明](https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/connect-to-linux-instance.htm)

**完成标志：** 命令提示符变成类似 `ubuntu@auto-quant:~$` 的内容。这个终端现在控制的是**云电脑**，而不是你自己的电脑。请保持它打开；主安装指南将它称为 **窗口 A — Ubuntu**。

<a id="oci-check"></a>
## 6. 检查是否准备就绪

**操作位置：窗口 A — Ubuntu。** 逐行粘贴以下命令：

```bash
uname -m
. /etc/os-release
printf '%s %s\n' "$ID" "$VERSION_ID"
python3.12 --version
timedatectl status
```

| 检查项 | 应看到的结果 |
| --- | --- |
| 电脑架构 | `aarch64` |
| 操作系统 | `ubuntu 24.04` |
| Python | `Python 3.12.x`，x 的位置是数字 |
| 时钟 | `System clock synchronized: yes` |

`. /etc/os-release` 这一行通常不会显示任何内容。如果时钟同步显示 no，请运行下面的命令，稍等片刻后重新运行 `timedatectl status`：

```bash
sudo timedatectl set-ntp true
```

如果其他结果不符，请先停止安装并检查实例镜像和机型。不要将系统默认 Python 改成其他版本。

**本部分完成：** 返回[安装指南第 3 步——传送下载文件](SETUP.zh-CN.md#transfer)。窗口 A 保持 Ubuntu 连接，再在你自己的电脑上打开第二个终端来传送文件。

<a id="oci-help"></a>
## 遇到问题怎么办

| 现象 | 处理方法 |
| --- | --- |
| Oracle 拒绝注册或付款验证 | 向 Oracle 注册支持核对资料，Auto Quant 无法代替 Oracle 开通账户。 |
| “Out of capacity” | 尝试同一区域内其他可用域的 A1，或稍后再试；仍需使用 ARM64 机型。 |
| 找不到公网 IPv4 地址 | 检查实例使用的是公共子网，且已启用公网 IPv4 分配。`10.x.x.x` 是私网地址。 |
| SSH 连接超时 | 检查 Running 状态、公网 IP、公共子网，以及 22 端口规则中的地址是否仍是你当前的公网地址。切换 VPN/Wi-Fi 可能改变地址。 |
| “Identity file … not accessible” | 确认终端位于 Downloads，且私钥准确命名为 `auto-quant.key`。 |
| “Permission denied (publickey)” | 使用用户名 `ubuntu` 和这台实例对应的私钥，不要使用 `.pub` 文件。 |
| “UNPROTECTED PRIVATE KEY FILE” | Mac/Linux：运行上面的 `chmod` 命令。Windows：按下方说明修改权限。 |
| Windows 提示找不到 `ssh` | 在 Windows **Optional features（可选功能）**中安装 **OpenSSH Client（客户端）**，然后重新打开 PowerShell。[Microsoft 说明](https://learn.microsoft.com/en-us/windows-server/administration/openssh/openssh_install_firstuse) |
| Ubuntu 检查显示 `x86_64` 或其他版本 | 镜像或机型不符合此安装包要求，请先修正，再安装 Auto Quant。 |

对于 **Windows 私钥权限警告**，右键点击 `auto-quant.key` → **属性 → 安全 → 高级**。确认所有者是你自己的 Windows 账户。禁用继承并移除继承的权限；添加你自己的 Windows 账户，授予**读取**权限，并移除允许其他普通用户访问的条目。应用后重新连接。如果不确定哪个账户是自己的，请先请人协助确认，不要发送私钥文件。

求助时请提供步骤编号和错误文字。请隐藏密码、私钥、relay token 和一次性关联码。
