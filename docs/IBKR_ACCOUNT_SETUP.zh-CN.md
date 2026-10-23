# 准备 IBKR 专用账户及独立 Gateway 登录

[English](IBKR_ACCOUNT_SETUP.md) | 简体中文 | [返回安装指南](SETUP.zh-CN.md#prepare)

在 `./follow-stack setup` 中填写 IBKR 凭据前完成本流程。使用自己的浏览器和手机，
Codex／Claude Code 可以逐步解释界面。账户申请、个人资料、协议及身份验证由客户本人完成。
说明核对日期：2026 年 10 月 22 日（美国太平洋时间）；不同账户的界面可能略有差异。

## 1. 为 Auto Quant 开立附加账户

尚无 IBKR 账户时，先完成首次申请及验证，再用主用户名登录 **Client Portal（客户端）**。

1. 打开 **User icon（用户头像）→ Settings（设置）→ Trading（交易）→ Open an Additional Account（开立附加账户）**。
   部分界面在 Settings 中直接显示此入口。
2. 用自己的资料完成关联账户申请，自行选择账户类型、阅读协议；助手不得代填财务状况或投资经验。
   产品选择 **Futures（期货）**，如实填写期货经验年数、交易次数及知识程度。
   确有数年经验时选择相符区间，IBKR 自行审核资格；不得为获批而填写虚构经验。
3. 等待 IBKR 批准并激活，将其作为 Auto Quant 专用账户。已有合适的专用账户时核对并复用，不重复申请。

关联账户有独立账户 ID，实盘使用时需要单独入金；开立它不会自动生成第二个登录用户名。
本次安装仍从 **paper（模拟）**开始，开立实盘账户不代表同意入金、转账或实盘交易。
[IBKR 附加账户说明](https://www.ibkrguides.com/clientportal/createnewlinkedaccount.htm)。

**检查点：** 新账户已获批，或已有专用账户已确认；聊天仅记录完成状态，不记录账户 ID。

## 2. 为同一账户持有人创建第二用户名

1. 打开 **User icon → Settings → User & Access Rights → Users → “+” Add**。
   部分界面将页面称为 **Users & Access Rights（用户及访问权限）**。
2. 私密设置新用户名和密码；在“是否为主账户持有人的 secondary user（第二用户名）”处选择 **Yes**。
   此登录属于你本人，不要将 Auto Quant 或助手添加为用户。
3. 核对专用账户的访问权限，完成 IBKR 确认及安全验证设置。确认所需期货权限和行情权限；
   额外用户可能产生单独的行情订阅费用。
4. **主用户名留给手机／手动交易，第二用户名专供 OCI 上的 Gateway**；两组凭据均私密保存。

IBKR 每个用户名同一时间只允许一个交易会话。手机用 Gateway 的同一用户名登录交易，
可能将 OCI 上的 Gateway 踢下线。仅新增关联账户无法解决，两个交易会话必须使用不同用户名。
在手机上批准 IB Key 验证请求，与打开另一个手机交易会话是不同操作。
[IBKR 第二用户名说明](https://www.ibkrguides.com/clientportal/uar/addingusernamestoauser.htm)及
[会话规则](https://ibkrcampus.com/docs/web-api/authentication/sessions)。

**检查点：** 第二用户名可用、安全验证已完成，并已明确哪个登录专供 Gateway。
用户名和密码均不要发到聊天或写入进度记录。

## 3. 申请并核验期货交易权限

开户时选择 **Futures（期货）**，CME 的 MNQ／NQ 需相应 **United States（美国）**权限。
已有账户可到 **User icon → Settings → Trading → Trading Permissions → Request/Edit → Futures**。
如实填写经验／资料问卷，完成披露并保存。IBKR 同时考虑财务资料和投资目标，
选择某个经验年数并不保证获批。

**检查点：** 专用账户及 Gateway 用户的所需期货权限已批准。拒绝或待补资料时暂停，
由客户与 IBKR 处理；助手不能更改经验答案来使其“符合资格”。
[IBKR 交易权限说明](https://www.ibkrguides.com/clientportal/tradingpermissions.htm)。

## 4. 完成两份行情表单，并订阅 CME Level 1

**位置：Client Portal → User icon → Settings → Trading Platform → Market Data Subscriptions。**
核对这是为 Gateway 提供行情的订阅／用户名；手机另一个用户名有订阅，不代表 Gateway 有权限。

1. 找到 **Market Data API Acknowledgement**，点击 **齿轮／Configure**，阅读并完成表单后提交保存。
   部分页面称为 **Market Data API Agreement**。确认已完成，IBKR 可能要求每年重新确认。
2. 找到 **Market Data Subscriber Status**，点击其 **齿轮／Configure**，完成另一份表单。
   确实符合交易所定义的客户，在下拉菜单选择 **Non-Professional（非专业）**，如实回答问卷并提交，
   确认保存的状态。专业用户或资格不明确时，应填写正确状态并请 IBKR 确认适用订阅，
   不能默认所有客户都符合非专业收费条件。
3. 在 **Current Subscriptions** 点击 **齿轮／Configure**，进入
   **United States／North America → Level 1（Top of Book）**，勾选 **CME Real-Time (L1)**，
   也可能显示 **CME Real-Time Non-Professional Level 1**。本指南核对的非专业公开价格为 **每月 USD $1.55**。
   客户须核对实际报价、扣费账户及额外用户费用，自行接受循环订阅和交易所协议后再确认。
4. 完成后返回 Current Subscriptions，确认 CME Real-Time (L1) 已生效，并确认两份表单均已保存。
   仅订阅行情不代表完成 API 确认或订阅者状态表单。
5. 在下方 **Paper Trading Account** 设置核对模拟登录能使用实时行情，必要时完成行情共享。
   登录 Gateway 后再用正常的行情检查验证实际访问。

本流程使用 CME Level 1 为 MNQ／NQ 提供行情。资格或价格不同时，购买前向客户展示实际选项，
不要擅自替换为 Level 2 套餐，也不要把延迟报价当作实时就绪。
[IBKR 订阅步骤](https://www.ibkrguides.com/clientportal/usersettings/marketdatasubscriptions.htm)、
[订阅者状态](https://www.ibkrguides.com/clientportal/usersettings/marketdatasubscriberstatus.htm)、
[API 确认要求](https://ibkrcampus.com/docs/web-api/v1/endpoints/market-data/market-data-availability)及
[当前行情价格](https://www.interactivebrokers.com/en/pricing/market-data-pricing.php)。

**检查点：** API 确认已完成、真实订阅者状态已保存、Gateway 对应 CME Level 1 已生效，且客户接受循环费用。
仅记录完成／待处理，不记录个人问卷答案。

## 5. 运行向导前验证模拟登录

IBKR 模拟账户的用户名、密码及账户 ID 可能与实盘不同。创建实盘第二用户名，并不证明
它能访问模拟账户。登录实盘 Client Portal，打开 **User icon → Settings → Account Configuration →
Paper Trading Account（模拟交易账户）**，
核对本次安装对应的模拟登录和账户。需要单独创建或启用模拟登录时，先完成 IBKR 流程。
模拟登录专供 OCI，手机交易使用另一个用户名。
[IBKR 模拟账户设置说明](https://www.ibkrguides.com/clientportal/papertradingaccount.htm)。

确认 Gateway 登录能访问预期的 **paper** 账户，且期货权限、行情权限可用。
Gateway 向导填写已核验的模拟登录，执行器向导填写其模拟账户 ID；用户名与账户 ID 是不同字段。
不能因为模拟登录尚未准备好，就改填实盘凭据。

若缺少入口、审批未完成或用户名无权访问目标账户，暂停本检查点并请 IBKR 处理。
不要复用正在手机上交易的登录、强制踢掉其他会话或反复重启 Gateway 来绕过问题。

Gateway 连接后，**在执行器仍停止时**，用另一个用户名登录手机交易，再运行
`./follow-stack check`（原生包用 `./follow check`）：Gateway 必须保持连接，账户／行情检查应通过。
此步骤验证登录安排，不会提交交易订单；不能仅凭进程运行就标记通过。
之后返回[安装指南](SETUP.zh-CN.md)。
