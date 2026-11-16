# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Follow Executor contributors
"""The setup console's page, stylesheet and script.

Kept as Python strings so the bytecode wheel carries them without a separate
data-file step. The page loads nothing from the internet.
"""

HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="referrer" content="no-referrer">
<title>Auto Quant setup console</title>
<link rel="stylesheet" href="/app.css">
</head>
<body>
<header class="top">
  <div>
    <h1 id="title">Auto Quant setup console</h1>
    <p class="sub" id="subtitle"></p>
  </div>
  <div class="lang" role="group" aria-label="Language">
    <button type="button" data-lang="en">English</button>
    <button type="button" data-lang="zh">中文</button>
  </div>
</header>
<div class="layout">
  <nav class="steps" aria-label="Setup steps"><ol id="steps"></ol></nav>
  <main>
    <div id="banner" class="banner" hidden></div>
    <section id="screen" class="card" aria-live="polite"></section>
    <section id="settings" class="card" hidden></section>
    <section id="job" class="card output" hidden>
      <div class="output-head"><h2 id="job-title"></h2><span id="job-state" class="pill"></span></div>
      <pre id="job-lines" tabindex="0"></pre>
      <div id="job-report"></div>
    </section>
    <section id="logs" class="card output" hidden>
      <div class="output-head"><h2 id="logs-title"></h2><button type="button" id="logs-close" class="quiet"></button></div>
      <pre id="logs-lines" tabindex="0"></pre>
    </section>
    <section class="card tools">
      <h2 id="tools-title"></h2>
      <div id="tools" class="row"></div>
    </section>
  </main>
</div>
<script src="/app.js"></script>
</body>
</html>
"""

CSS = """:root {
  --bg: #f6f5f2; --surface: #ffffff; --text: #1d1d1b; --muted: #5f5e5a; --line: #dedcd5;
  --accent: #2f5bd3; --accent-text: #ffffff; --good: #1f7a3d; --warn: #9a5b00; --bad: #b3261e;
  --code-bg: #f0efea; --focus: #2f5bd3;
  color-scheme: light;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #161615; --surface: #1f1f1d; --text: #ecebe6; --muted: #a8a69e; --line: #3a3935;
    --accent: #8aa8ff; --accent-text: #0f1530; --good: #6fcf8f; --warn: #f0b45c; --bad: #ff8a80;
    --code-bg: #121211; --focus: #8aa8ff;
    color-scheme: dark;
  }
}
* { box-sizing: border-box; }
[hidden] { display: none !important; }
body { margin: 0; background: var(--bg); color: var(--text);
  font: 15px/1.5 system-ui, -apple-system, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif; }
h1 { font-size: 20px; margin: 0; }
h2 { font-size: 17px; margin: 0 0 8px; }
h3 { font-size: 15px; margin: 0 0 8px; }
p { margin: 0 0 12px; }
.top { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px;
  padding: 16px 24px; border-bottom: 1px solid var(--line); background: var(--surface); }
.sub { color: var(--muted); margin: 2px 0 0; font-size: 13px; }
.lang { display: flex; gap: 4px; flex-shrink: 0; }
.layout { display: grid; grid-template-columns: 260px minmax(0, 1fr); gap: 24px;
  max-width: 1100px; margin: 0 auto; padding: 24px; }
.steps ol { list-style: none; margin: 0; padding: 0; position: sticky; top: 16px; }
.steps li { display: flex; gap: 10px; align-items: flex-start; padding: 8px 10px; border-radius: 8px; color: var(--muted); }
.steps li.current { background: var(--surface); color: var(--text); font-weight: 600; outline: 1px solid var(--line); }
.steps li.done { color: var(--text); }
.mark { width: 22px; height: 22px; border-radius: 50%; border: 1.5px solid var(--line); flex-shrink: 0;
  display: inline-flex; align-items: center; justify-content: center; font-size: 12px; }
.done .mark { border-color: var(--good); color: var(--good); }
.current .mark { border-color: var(--accent); color: var(--accent); }
main { display: flex; flex-direction: column; gap: 16px; min-width: 0; }
.card { background: var(--surface); border: 1px solid var(--line); border-radius: 12px; padding: 20px; }
.banner { border-radius: 12px; padding: 12px 16px; border: 1px solid var(--warn); color: var(--warn); background: var(--surface); }
.row { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
button { font: inherit; padding: 8px 14px; border-radius: 8px; border: 1px solid var(--line);
  background: var(--surface); color: var(--text); cursor: pointer; }
button.primary { background: var(--accent); color: var(--accent-text); border-color: var(--accent); font-weight: 600; }
button.danger { border-color: var(--bad); color: var(--bad); }
button.quiet { border-color: transparent; color: var(--muted); }
button[aria-pressed="true"] { border-color: var(--accent); color: var(--accent); }
button:disabled { opacity: .5; cursor: not-allowed; }
button:focus-visible, input:focus-visible, select:focus-visible, pre:focus-visible { outline: 2px solid var(--focus); outline-offset: 2px; }
form { display: grid; gap: 14px; }
fieldset { border: 1px solid var(--line); border-radius: 10px; padding: 12px 14px; margin: 0; display: grid; gap: 10px; }
legend { padding: 0 6px; font-weight: 600; }
label { display: grid; gap: 4px; font-weight: 600; }
label.inline { display: flex; gap: 8px; align-items: center; font-weight: 400; }
.hint { font-weight: 400; color: var(--muted); font-size: 13px; }
input, select { font: inherit; padding: 8px 10px; border-radius: 8px; border: 1px solid var(--line);
  background: var(--bg); color: var(--text); width: 100%; max-width: 420px; }
input[type="radio"], input[type="checkbox"] { width: auto; }
.error { color: var(--bad); font-weight: 600; }
.ok { color: var(--good); font-weight: 600; }
.warn { color: var(--warn); }
.phrase { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; background: var(--code-bg);
  padding: 2px 6px; border-radius: 6px; }
details > summary { cursor: pointer; font-weight: 600; margin: 4px 0; }
.subsection { border-top: 1px solid var(--line); margin-top: 16px; padding-top: 16px; }
.code-big { font: 600 20px/1.4 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; background: var(--code-bg);
  padding: 8px 12px; border-radius: 8px; display: inline-block; user-select: all; }
.facts { display: grid; grid-template-columns: max-content 1fr; gap: 4px 16px; margin: 0 0 12px; }
.facts dt { color: var(--muted); }
.facts dd { margin: 0; }
.output-head { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.pill { font-size: 13px; padding: 2px 10px; border-radius: 999px; border: 1px solid var(--line); color: var(--muted); }
pre { background: var(--code-bg); border-radius: 8px; padding: 12px; margin: 8px 0 0; max-height: 360px;
  overflow: auto; white-space: pre-wrap; word-break: break-word;
  font: 12.5px/1.45 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
ul.problems { margin: 8px 0 0; padding-left: 20px; }
@media (max-width: 760px) {
  .top { padding: 12px 16px; }
  .layout { grid-template-columns: 1fr; padding: 16px; gap: 16px; }
  .steps ol { position: static; display: flex; flex-wrap: wrap; gap: 4px; }
  .steps li { padding: 4px 8px; }
  .steps li .label { display: none; }
  .steps li.current .label { display: inline; }
  .card { padding: 16px; }
}
"""

JS = r"""'use strict';
const STRINGS = {
  en: {
    title: 'Auto Quant setup console',
    subtitle: 'Private to this VM. Setup never starts trading by itself.',
    step_docker: 'Docker and startup', step_image: 'Executor image', step_account: 'Account and sizing',
    step_gateway: 'Gateway login settings', step_login: 'Approve on your phone', step_readiness: 'Readiness check',
    step_trading: 'Start following',
    tools: 'Tools', tool_doctor: 'Setup summary', tool_status: 'Executor status', tool_service: 'Service status',
    tool_gateway_status: 'Gateway status', tool_check: 'Readiness check', tool_logs: 'Executor logs',
    tool_gateway_logs: 'Gateway logs', close_logs: 'Close logs',
    running: 'Running…', finished_ok: 'Finished', finished_fail: 'Stopped (exit {code})', waiting: 'Waiting for you',
    session_lost: 'This page is not connected. Use the link printed in your SSH window. Each link works once; to get a new one, close the console with Ctrl+C and run it again.',
    busy: 'Another action is running. Wait for it to finish.',
    continue_title: 'Continue setup',
    continue_body: 'Setup checks this VM and continues from the first step that is not finished. It stops to ask you for anything it needs.',
    continue_button: 'Continue setup',
    next_step: 'Next step: {step}',
    failed_title: 'Setup stopped',
    failed_body: 'Read the message in the output below, fix what it describes, then continue. Saved settings are kept.',
    docker_install_title: 'Install Docker',
    docker_install_body: 'Docker is not installed. Setup installs Docker Engine from Docker’s official Ubuntu repository using sudo. The VM then needs one restart.',
    docker_permissions_title: 'Finish Docker permissions',
    docker_permissions_body: 'Docker is installed, but this login’s Docker group setup is incomplete. Setup finishes it using sudo. The VM then needs one restart.',
    linger_title: 'Keep services running after logout',
    linger_body: 'Setup enables services for your login after logout and reboot, using sudo. Without this, Gateway and the executor stop when you disconnect.',
    approve: 'Approve and continue', not_now: 'Not now',
    reboot_title: 'Restart the VM',
    reboot_body: 'The change needs a restart. Restarting closes this console and your SSH connection. Wait a minute or two, run the same SSH command again, and open the new link it prints.',
    reboot_button: 'Restart VM now', reboot_confirm: 'Restart the VM now? The console and your SSH connection will close.',
    account_title: 'Account and sizing',
    account_body: 'Start with your paper account. Your relay token is saved only on this VM, readable only by your login.',
    mode: 'Account mode', mode_paper: 'Paper (recommended to start)', mode_live: 'Live (real money)',
    account: 'IBKR account ID', account_hint: 'For example DU1234567 for a paper account.',
    sizing: 'Sizing', sizing_balance: 'Balance sizing: NQ plus an MNQ remainder, sized from your NetLiquidation at each entry',
    sizing_mnq: 'Fixed number of MNQ contracts', sizing_nq: 'Fixed number of NQ contracts',
    fraction: 'Leverage fraction', fraction_hint: 'Above 0 and at most 1. For example 0.5 follows half of the leader’s balance sizing.',
    quantity: 'Number of contracts', quantity_hint: 'A whole number from 1 to 10.',
    token: 'Personal relay token', token_hint: 'From Auto Quant. Paste it here only, never into chat.',
    live_phrase: 'Type {phrase} to configure real-money trading',
    save_account: 'Save account and continue',
    gateway_title: 'Gateway login settings',
    gateway_body: 'IBC logs in to IB Gateway with a login stored privately on this VM. You still approve each login in IBKR Mobile. Use a dedicated Gateway username, not the one you use for phone trading.',
    timezone: 'Schedule timezone', timezone_hint: 'An IANA name, for example America/New_York or Asia/Shanghai.',
    daily: 'Daily automatic restart (HH:MM)', daily_hint: 'Choose a time outside active trading.',
    sunday: 'Sunday mobile approval time (HH:MM)', sunday_hint: 'Be ready to approve the IBKR Mobile prompt at this time each Sunday.',
    vnc: 'Enable the private recovery desktop (recommended)',
    vnc_hint: 'Lets you see and close Gateway dialogs through your SSH connection.',
    vnc_password: 'Recovery desktop password', vnc_password_hint: 'Exactly 8 characters, letters, digits or symbols, no spaces. Not your IBKR password.',
    vnc_confirm: 'Confirm recovery desktop password',
    username: 'IBKR login username (Gateway)', password: 'IBKR password',
    gateway_live: 'Type LIVE to enable automatic real-account login',
    save_gateway: 'Save Gateway login and continue',
    login_title: 'Approve the login on your phone',
    login_body: 'Gateway is starting and will ask IBKR Mobile to approve the login. Approve the newest prompt on your phone. Then check readiness.',
    login_vnc: 'If a Gateway dialog needs attention, open your VNC viewer at localhost:5901 (TigerVNC: localhost::5901) and use the recovery desktop password. Your SSH command already forwards this port.',
    login_ready: 'Gateway is logged in – check readiness',
    start_title: 'Start following',
    start_body: 'Readiness checks passed. Starting checks readiness again, enables automatic recovery after reboot and begins following trading signals.',
    start_type: 'To start, type {phrase}', start_button: 'Start following',
    start_mismatch: 'Type the phrase exactly as shown.',
    dash_title: 'Following is running',
    dash_body: 'The executor and Gateway keep running after you close this page or disconnect.',
    stop_button: 'Stop following (positions stay open)',
    stop_confirm: 'Stop following? This does not close positions or cancel broker orders. A stopped executor cannot manage exits. Stop only while flat unless you are handling the position yourself.',
    fact_mode: 'Mode', fact_size: 'Size', fact_account: 'Account', fact_executor: 'Executor service', fact_gateway: 'Gateway service',
    problems: 'Problems reported', no_problems: 'No problems reported.',
    required: 'Fill in {field}.', bad_fraction: 'Enter a number above 0 and at most 1.',
    bad_quantity: 'Enter a whole number from 1 to 10.', bad_token: 'Paste the token without spaces.',
    bad_time: 'Use HH:MM, for example 23:45.', bad_vnc: 'Use exactly 8 printable characters without spaces, the same in both boxes.',
    bad_live: 'Type the phrase exactly as shown.',
    host_problem: 'This computer is not a supported VM: {problem}',
    settings_title: 'Settings',
    settings_running: 'Stop following while flat to change sizing or Discord notifications.',
    sizing_change_title: 'Change sizing',
    sizing_change_body: 'The change is checked against the journal and IBKR: the account must be flat, with no halt and no working orders, so keep Gateway logged in. It takes effect at the next start and never resizes an open trade.',
    current_size: 'Current size: {size}',
    nq_price: 'Approximate current NQ price (optional)', nq_price_hint: 'For a size preview at your IBKR NetLiquidation, using example weights.',
    change_sizing: 'Change sizing', bad_price: 'Enter a positive number, or leave it empty.',
    discord_title: 'Discord notifications (optional)',
    discord_body: 'Private DMs from AQ Bot about trades and service health. Join your provider\u2019s Auto Quant Discord server first.',
    discord_disclosure: 'Discord notifications share instrument, position, quantity, entry/exit prices, gross profit/loss, service/Gateway health, liveness heartbeats and event times with Auto Quant and Discord. IBKR credentials and account ID are not included.',
    discord_agree: 'Type LINK to agree and pair your Discord account', discord_link: 'Get pairing code',
    discord_status: 'Discord status', discord_enable: 'Enable notifications', discord_enable_hint: 'Enable only after you receive the test DM. Takes effect at the next start.',
    discord_unlink: 'Unlink Discord', discord_unlink_confirm: 'Unlink Discord and cancel pending messages?',
    discord_code: 'In Discord, send this command to AQ Bot within 10 minutes:',
    advanced_title: 'Advanced recovery',
    resume_body: 'Halt recovery is for deliberate recovery after you have inspected the account, not a routine restart. The running executor takes ownership of the broker\u2019s current position on its next step and aligns it with the latest target, which may close it.',
    halt_reason: 'Last reported halt: {reason}', halt_unknown: 'Run Executor status to see whether the executor is halted.', halt_none: 'Last status: not halted.',
    resume_type: 'Type RESUME to request halt recovery', resume_button: 'Request halt recovery',
  },
  zh: {
    title: 'Auto Quant 安装控制台',
    subtitle: '仅在本 VM 内可用。安装本身不会开始交易。',
    step_docker: 'Docker 与开机运行', step_image: '执行器镜像', step_account: '账户与仓位大小',
    step_gateway: 'Gateway 登录设置', step_login: '在手机上批准', step_readiness: '就绪检查',
    step_trading: '开始跟单',
    tools: '工具', tool_doctor: '安装概况', tool_status: '执行器状态', tool_service: '服务状态',
    tool_gateway_status: 'Gateway 状态', tool_check: '就绪检查', tool_logs: '执行器日志',
    tool_gateway_logs: 'Gateway 日志', close_logs: '关闭日志',
    running: '运行中…', finished_ok: '已完成', finished_fail: '已停止（退出码 {code}）', waiting: '等待你的操作',
    session_lost: '此页面未连接。请使用 SSH 窗口中打印的链接。每个链接只能使用一次；如需新链接，请按 Ctrl+C 关闭控制台后重新运行。',
    busy: '另一个操作正在运行，请等待其完成。',
    continue_title: '继续安装',
    continue_body: '安装会检查本 VM，并从第一个未完成的步骤继续。需要你提供信息时会暂停询问。',
    continue_button: '继续安装',
    next_step: '下一步：{step}',
    failed_title: '安装已暂停',
    failed_body: '请阅读下方输出中的信息，按提示处理后再继续。已保存的设置会保留。',
    docker_install_title: '安装 Docker',
    docker_install_body: '尚未安装 Docker。安装程序将使用 sudo 从 Docker 官方 Ubuntu 软件源安装 Docker Engine，之后需要重启一次 VM。',
    docker_permissions_title: '完成 Docker 权限设置',
    docker_permissions_body: 'Docker 已安装，但当前登录用户的 Docker 用户组设置尚未完成。安装程序将使用 sudo 完成设置，之后需要重启一次 VM。',
    linger_title: '退出登录后保持服务运行',
    linger_body: '安装程序将使用 sudo 让你的登录用户在退出登录和重启后继续运行服务。否则断开连接后 Gateway 和执行器会停止。',
    approve: '同意并继续', not_now: '暂不',
    reboot_title: '重启 VM',
    reboot_body: '此更改需要重启。重启会关闭此控制台和 SSH 连接。请等待一两分钟，再次运行同一条 SSH 命令，并打开它打印的新链接。',
    reboot_button: '立即重启 VM', reboot_confirm: '现在重启 VM？控制台和 SSH 连接将会关闭。',
    account_title: '账户与仓位大小',
    account_body: '请先使用模拟账户。个人令牌只保存在本 VM 上，仅你的登录用户可读取。',
    mode: '账户模式', mode_paper: '模拟账户（建议先用）', mode_live: '真实账户（真实资金）',
    account: 'IBKR 账户 ID', account_hint: '例如模拟账户 DU1234567。',
    sizing: '仓位大小', sizing_balance: '按余额计算：NQ 加 MNQ 补足，每次入场按你的 NetLiquidation 计算',
    sizing_mnq: '固定数量的 MNQ 合约', sizing_nq: '固定数量的 NQ 合约',
    fraction: '杠杆比例', fraction_hint: '大于 0 且不超过 1。例如 0.5 表示跟随领投方按余额计算仓位的一半。',
    quantity: '合约数量', quantity_hint: '1 到 10 的整数。',
    token: '个人令牌', token_hint: '由 Auto Quant 提供。只粘贴到这里，切勿粘贴到聊天中。',
    live_phrase: '输入 {phrase} 以设置真实资金交易',
    save_account: '保存账户并继续',
    gateway_title: 'Gateway 登录设置',
    gateway_body: 'IBC 使用私密保存在本 VM 上的登录信息登录 IB Gateway，每次登录仍需你在 IBKR Mobile 中批准。请为 Gateway 使用专用用户名，不要与手机交易使用的用户名相同。',
    timezone: '时间表时区', timezone_hint: 'IANA 时区名称，例如 America/New_York 或 Asia/Shanghai。',
    daily: '每日自动重启时间（HH:MM）', daily_hint: '请选择非活跃交易时段。',
    sunday: '周日手机批准时间（HH:MM）', sunday_hint: '每周日此时请准备好在 IBKR Mobile 中批准登录。',
    vnc: '启用私密恢复桌面（建议）',
    vnc_hint: '可通过 SSH 连接查看并关闭 Gateway 弹窗。',
    vnc_password: '恢复桌面密码', vnc_password_hint: '恰好 8 个字符（字母、数字或符号），不含空格。不是你的 IBKR 密码。',
    vnc_confirm: '确认恢复桌面密码',
    username: 'IBKR 登录用户名（Gateway）', password: 'IBKR 密码',
    gateway_live: '输入 LIVE 以启用真实账户自动登录',
    save_gateway: '保存 Gateway 登录并继续',
    login_title: '在手机上批准登录',
    login_body: 'Gateway 正在启动，会请求 IBKR Mobile 批准登录。请在手机上批准最新的请求，然后进行就绪检查。',
    login_vnc: '如果 Gateway 弹窗需要处理，请用 VNC 查看器打开 localhost:5901（TigerVNC：localhost::5901），并输入恢复桌面密码。你的 SSH 命令已转发此端口。',
    login_ready: 'Gateway 已登录 – 进行就绪检查',
    start_title: '开始跟单',
    start_body: '就绪检查已通过。开始时会再次进行就绪检查，启用重启后的自动恢复，并开始跟随交易信号。',
    start_type: '如要开始，请输入 {phrase}', start_button: '开始跟单',
    start_mismatch: '请完全按显示内容输入。',
    dash_title: '跟单正在运行',
    dash_body: '关闭此页面或断开连接后，执行器和 Gateway 会继续运行。',
    stop_button: '停止跟单（持仓保留）',
    stop_confirm: '停止跟单？这不会平仓，也不会撤销券商订单。停止后的执行器无法管理离场。除非你自行处理持仓，否则只在空仓时停止。',
    fact_mode: '模式', fact_size: '仓位', fact_account: '账户', fact_executor: '执行器服务', fact_gateway: 'Gateway 服务',
    problems: '报告的问题', no_problems: '未报告问题。',
    required: '请填写{field}。', bad_fraction: '请输入大于 0 且不超过 1 的数字。',
    bad_quantity: '请输入 1 到 10 的整数。', bad_token: '请粘贴不含空格的令牌。',
    bad_time: '请使用 HH:MM 格式，例如 23:45。', bad_vnc: '请在两个输入框中输入相同的 8 个可打印字符，不含空格。',
    bad_live: '请完全按显示内容输入。',
    host_problem: '此计算机不是受支持的 VM：{problem}',
    settings_title: '设置',
    settings_running: '如需更改仓位大小或 Discord 通知，请在空仓时先停止跟单。',
    sizing_change_title: '更改仓位大小',
    sizing_change_body: '更改前会核对交易日志和 IBKR：账户必须空仓、未暂停且没有未完成订单，因此请保持 Gateway 已登录。更改在下次启动时生效，不会调整已开仓的交易。',
    current_size: '当前仓位：{size}',
    nq_price: 'NQ 大致当前价格（可选）', nq_price_hint: '用于按你的 IBKR NetLiquidation 和示例权重预览仓位。',
    change_sizing: '更改仓位大小', bad_price: '请输入正数，或留空。',
    discord_title: 'Discord 通知（可选）',
    discord_body: 'AQ Bot 会私信你交易和服务状态。请先加入服务提供方的 Auto Quant Discord 服务器。',
    discord_disclosure: 'Discord 通知会与 Auto Quant 和 Discord 共享品种、持仓、数量、入场/离场价格、毛盈亏、服务/Gateway 健康状态、存活心跳和事件时间。不包括 IBKR 凭据和账户 ID。',
    discord_agree: '输入 LINK 表示同意并配对你的 Discord 账户', discord_link: '获取配对码',
    discord_status: 'Discord 状态', discord_enable: '启用通知', discord_enable_hint: '收到测试私信后再启用。下次启动时生效。',
    discord_unlink: '解除 Discord 关联', discord_unlink_confirm: '解除 Discord 关联并取消待发送的消息？',
    discord_code: '请在 10 分钟内于 Discord 中向 AQ Bot 发送以下命令：',
    advanced_title: '高级恢复',
    resume_body: '暂停恢复用于在检查账户后有意进行的恢复，不是常规重启。运行中的执行器会在下一步接管券商当前持仓，并按最新目标调整，可能会平仓。',
    halt_reason: '最近报告的暂停原因：{reason}', halt_unknown: '请运行“执行器状态”查看执行器是否已暂停。', halt_none: '最近状态：未暂停。',
    resume_type: '输入 RESUME 以请求暂停恢复', resume_button: '请求暂停恢复',
  },
};

let lang = 'en';
try { const saved = localStorage.getItem('follow-console-lang'); if (saved in STRINGS) lang = saved; else if ((navigator.language || '').toLowerCase().startsWith('zh')) lang = 'zh'; } catch (e) { /* storage unavailable */ }
const t = (key, values) => {
  let text = (STRINGS[lang] && STRINGS[lang][key]) || STRINGS.en[key] || key;
  for (const [name, value] of Object.entries(values || {})) text = text.split('{' + name + '}').join(String(value));
  return text;
};

let csrf = '';
let state = null;
let screen = null;      // explicit screen chosen by the last action's result
let lastJob = null;     // {id, kind}
let logsJob = null;
let rendered = '';     // the screen currently shown, so polling never wipes a form
let renderedSettings = '';
let lastHalt;          // undefined until a status report is seen
const $ = (id) => document.getElementById(id);

function el(tag, attrs, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === null || value === undefined || value === false) continue;
    if (key === 'class') node.className = value;
    else if (key.startsWith('on')) node.addEventListener(key.slice(2), value);
    else if (value === true) node.setAttribute(key, '');
    else node.setAttribute(key, value);
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

async function api(path, body) {
  const options = body === undefined ? { credentials: 'same-origin' } : {
    method: 'POST', credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', 'X-Console-CSRF': csrf },
    body: JSON.stringify(body),
  };
  const response = await fetch(path, options);
  let data = {};
  try { data = await response.json(); } catch (e) { data = {}; }
  if (!response.ok) { const error = new Error(data.error || response.statusText); error.status = response.status; throw error; }
  return data;
}

async function connect() {
  const match = location.hash.match(/token=([A-Za-z0-9_-]+)/);
  if (match) {
    history.replaceState(null, '', location.pathname);
    try { csrf = (await api('/api/session', { token: match[1] })).csrf; return true; } catch (e) { /* fall through */ }
  }
  try { csrf = (await api('/api/session')).csrf; return true; } catch (e) { return false; }
}

function steps() {
  const f = state.facts, r = state.readiness;
  return [
    { id: 'docker', done: f.docker_installed && !f.docker_problem && f.lingering },
    { id: 'image', done: f.image_installed },
    { id: 'account', done: f.config_saved },
    { id: 'gateway', done: f.gateway_saved && f.gateway_unit_installed },
    { id: 'login', done: f.gateway_service === 'active' && !!(r && r.passed) || f.executor_service === 'active' },
    { id: 'readiness', done: !!(r && r.passed) || f.executor_service === 'active' },
    { id: 'trading', done: f.executor_service === 'active' },
  ];
}

function currentScreen() {
  const f = state.facts;
  if (f.executor_service === 'active') return 'dashboard';
  if (screen) return screen;
  if (state.readiness && state.readiness.passed && f.config_saved) return 'start';
  return 'continue';
}

function renderSteps() {
  const list = $('steps');
  list.replaceChildren();
  const all = steps();
  const firstOpen = all.findIndex((s) => !s.done);
  all.forEach((s, i) => {
    const cls = s.done ? 'done' : (i === firstOpen ? 'current' : '');
    list.append(el('li', { class: cls, 'aria-current': i === firstOpen ? 'step' : null },
      el('span', { class: 'mark', 'aria-hidden': 'true' }, s.done ? '✓' : String(i + 1)),
      el('span', { class: 'label' }, t('step_' + s.id))));
  });
}

function put(node, items) { node.replaceChildren(...items.flat().filter((item) => item !== null && item !== undefined && item !== false)); }

function busy() { return !!(state && state.job && !state.job.done); }

function actionButton(label, onclick, cls) {
  return el('button', { type: 'button', class: cls || '', onclick, disabled: busy() }, label);
}

function render(force) {
  document.documentElement.lang = lang === 'zh' ? 'zh-CN' : 'en';
  document.title = t('title');
  $('title').textContent = t('title');
  $('subtitle').textContent = t('subtitle');
  $('tools-title').textContent = t('tools');
  $('logs-close').textContent = t('close_logs');
  for (const button of document.querySelectorAll('[data-lang]')) button.setAttribute('aria-pressed', String(button.dataset.lang === lang));
  if (!state) return;
  const banner = $('banner');
  banner.hidden = !state.facts.host_problem;
  banner.textContent = state.facts.host_problem ? t('host_problem', { problem: state.facts.host_problem }) : '';
  renderSteps();
  renderTools();
  const box = $('screen');
  const name = currentScreen() + (busy() ? ':busy' : '');
  if (!force && name === rendered && box.querySelector('form')) return; // keep what is being typed
  rendered = name;
  put(box, screenContent(currentScreen()));
  renderSettings(force);
}

function renderSettings(force) {
  const f = state.facts;
  const card = $('settings');
  card.hidden = !f.config_saved;
  if (!f.config_saved) return;
  const key = [f.executor_service, busy(), lastHalt, f.config && f.config.size].join('|');
  if (!force && key === renderedSettings && card.querySelector('form')) return;
  renderedSettings = key;
  const open = !!(card.querySelector('details') && card.querySelector('details').open);
  const running = f.executor_service === 'active';
  put(card, [
    el('h2', {}, t('settings_title')),
    running ? el('p', { class: 'hint' }, t('settings_running')) : [sizingForm(), discordSection()],
    advancedSection(open),
  ]);
}

function sizingForm() {
  const f = state.facts;
  const radio = (value, key, checked) => el('label', { class: 'inline' }, el('input', { type: 'radio', name: 'sizing', value, checked }), t(key));
  const balance = !f.config || f.config.size.startsWith('BALANCE');
  const form = el('form', { novalidate: true },
    el('fieldset', {}, el('legend', {}, t('sizing')), radio('balance', 'sizing_balance', balance),
      radio('MNQ', 'sizing_mnq', false), radio('NQ', 'sizing_nq', false)),
    el('div', { class: 'balance-only' },
      field('fraction', el('input', { name: 'fraction', inputmode: 'decimal', value: balance && f.config ? f.config.size.split(' ')[1] : '0.5' }), 'fraction_hint'),
      field('nq_price', el('input', { name: 'nq_price', inputmode: 'decimal' }), 'nq_price_hint')),
    el('div', { class: 'fixed-only', hidden: true }, field('quantity', el('input', { name: 'quantity', inputmode: 'numeric', value: '1' }), 'quantity_hint')),
    el('p', { class: 'error', role: 'alert', 'data-error': 'sizing' }),
    el('div', { class: 'row' }, el('button', { type: 'submit', class: 'primary', disabled: busy() }, t('change_sizing'))));
  const sync = () => {
    const isBalance = new FormData(form).get('sizing') === 'balance';
    form.querySelector('.balance-only').hidden = !isBalance;
    form.querySelector('.fixed-only').hidden = isBalance;
  };
  form.addEventListener('input', sync);
  form.addEventListener('submit', (event) => {
    event.preventDefault();
    const data = new FormData(form);
    const error = form.querySelector('[data-error]');
    const body = { name: 'settings', sizing: String(data.get('sizing')) };
    if (body.sizing === 'balance') {
      body.fraction = String(data.get('fraction') || '').trim();
      if (!(+body.fraction > 0 && +body.fraction <= 1)) { error.textContent = t('bad_fraction'); return; }
      body.nq_price = String(data.get('nq_price') || '').trim();
      if (body.nq_price && !(+body.nq_price > 0)) { error.textContent = t('bad_price'); return; }
    } else {
      body.quantity = String(data.get('quantity') || '').trim();
      if (!/^\d+$/.test(body.quantity) || +body.quantity < 1 || +body.quantity > 10) { error.textContent = t('bad_quantity'); return; }
    }
    error.textContent = '';
    commandWith(body);
  });
  sync();
  return el('div', {},
    el('h3', {}, t('sizing_change_title')),
    f.config ? el('p', {}, t('current_size', { size: f.config.size })) : null,
    el('p', { class: 'hint' }, t('sizing_change_body')), form);
}

function discordSection() {
  const agree = el('input', { name: 'agree', autocomplete: 'off', spellcheck: 'false' });
  const form = el('form', { novalidate: true },
    el('label', {}, t('discord_agree'), agree),
    el('div', { class: 'row' }, el('button', { type: 'submit', disabled: busy() }, t('discord_link'))));
  form.addEventListener('submit', (event) => {
    event.preventDefault();
    if (agree.value.trim() !== 'LINK') { alert(t('bad_live')); return; }
    commandWith({ name: 'discord-link', agree: 'LINK' });
  });
  return el('div', { class: 'subsection' },
    el('h3', {}, t('discord_title')), el('p', {}, t('discord_body')), el('p', { class: 'hint' }, t('discord_disclosure')), form,
    el('p', { class: 'hint' }, t('discord_enable_hint')),
    el('div', { class: 'row' },
      actionButton(t('discord_status'), () => command('discord-status')),
      actionButton(t('discord_enable'), () => command('discord-enable')),
      actionButton(t('discord_unlink'), () => { if (confirm(t('discord_unlink_confirm'))) command('discord-unlink'); }, 'quiet')));
}

function advancedSection(open) {
  const typed = el('input', { name: 'confirm', autocomplete: 'off', spellcheck: 'false' });
  const form = el('form', { novalidate: true },
    el('label', {}, t('resume_type'), typed),
    el('div', { class: 'row' }, el('button', { type: 'submit', class: 'danger', disabled: busy() }, t('resume_button'))));
  form.addEventListener('submit', (event) => {
    event.preventDefault();
    if (typed.value.trim() !== 'RESUME') { alert(t('bad_live')); return; }
    commandWith({ name: 'resume', confirm: 'RESUME' });
  });
  const halt = lastHalt === undefined ? t('halt_unknown') : lastHalt ? t('halt_reason', { reason: lastHalt }) : t('halt_none');
  return el('details', { class: 'subsection', open }, el('summary', {}, t('advanced_title')),
    el('p', {}, t('resume_body')), el('p', { class: lastHalt ? 'warn' : 'hint' }, halt),
    el('div', { class: 'row' }, actionButton(t('tool_status'), () => command('status'))), form);
}

function renderTools() {
  const f = state.facts;
  const stopped = f.executor_service !== 'active';
  put($('tools'), [
    actionButton(t('tool_doctor'), () => command('doctor')),
    actionButton(t('tool_status'), () => command('status')),
    actionButton(t('tool_service'), () => command('service-status')),
    f.gateway_saved ? actionButton(t('tool_gateway_status'), () => command('gateway-status')) : null,
    stopped && f.config_saved ? actionButton(t('tool_check'), () => command('check')) : null,
    f.config_saved ? el('button', { type: 'button', onclick: () => openLogs('executor') }, t('tool_logs')) : null,
    f.gateway_saved ? el('button', { type: 'button', onclick: () => openLogs('gateway') }, t('tool_gateway_logs')) : null,
  ]);
}

function nextStepName() {
  const open = steps().find((s) => !s.done);
  return open ? t('step_' + open.id) : '';
}

function consent(key) {
  return [
    el('h2', {}, t(key + '_title')),
    el('p', {}, t(key + '_body')),
    el('div', { class: 'row' },
      actionButton(t('approve'), () => runSetup({ [key]: 'y' }), 'primary'),
      actionButton(t('not_now'), () => { screen = null; render(true); }, 'quiet')),
  ];
}

function screenContent(name) {
  const f = state.facts;
  switch (name) {
    case 'need:docker_install': return consent('docker_install');
    case 'need:docker_permissions': return consent('docker_permissions');
    case 'need:linger': return consent('linger');
    case 'need:account': return accountForm();
    case 'need:gateway': return gatewayForm();
    case 'need:gateway_ready': return loginScreen();
    case 'reboot': return [
      el('h2', {}, t('reboot_title')), el('p', {}, t('reboot_body')),
      el('div', { class: 'row' }, actionButton(t('reboot_button'), () => { if (confirm(t('reboot_confirm'))) runSetupAction('reboot', {}); }, 'primary')),
    ];
    case 'failed': return [
      el('h2', {}, t('failed_title')), el('p', {}, t('failed_body')),
      el('div', { class: 'row' }, actionButton(t('continue_button'), () => runSetup({}), 'primary')),
    ];
    case 'start': return startScreen();
    case 'dashboard': return dashboard();
    default: return [
      el('h2', {}, t('continue_title')),
      el('p', {}, t('continue_body')),
      nextStepName() ? el('p', { class: 'hint' }, t('next_step', { step: nextStepName() })) : null,
      el('div', { class: 'row' }, actionButton(t('continue_button'), () => runSetup({}), 'primary')),
    ];
  }
}

function field(labelKey, input, hintKey) {
  return el('label', {}, t(labelKey), input, hintKey ? el('span', { class: 'hint' }, t(hintKey)) : null);
}

function formError() { return el('p', { class: 'error', role: 'alert', id: 'form-error' }); }
function showError(message) { const box = $('form-error'); if (box) box.textContent = message; }

function accountForm() {
  const mode = (value, key, checked) => el('label', { class: 'inline' },
    el('input', { type: 'radio', name: 'mode', value, checked }), t(key));
  const live = el('label', { hidden: true, id: 'live-box' }, el('span', { id: 'live-label' }), el('input', { name: 'live', autocomplete: 'off', spellcheck: 'false' }));
  const form = el('form', { novalidate: true },
    el('fieldset', {}, el('legend', {}, t('mode')), mode('paper', 'mode_paper', true), mode('live', 'mode_live', false)),
    field('account', el('input', { name: 'account', autocomplete: 'off', spellcheck: 'false', required: true }), 'account_hint'),
    el('fieldset', {}, el('legend', {}, t('sizing')),
      el('label', { class: 'inline' }, el('input', { type: 'radio', name: 'sizing', value: 'balance', checked: true }), t('sizing_balance')),
      el('label', { class: 'inline' }, el('input', { type: 'radio', name: 'sizing', value: 'MNQ' }), t('sizing_mnq')),
      el('label', { class: 'inline' }, el('input', { type: 'radio', name: 'sizing', value: 'NQ' }), t('sizing_nq'))),
    el('div', { id: 'fraction-box' }, field('fraction', el('input', { name: 'fraction', inputmode: 'decimal', value: '0.5' }), 'fraction_hint')),
    el('div', { id: 'quantity-box', hidden: true }, field('quantity', el('input', { name: 'quantity', inputmode: 'numeric', value: '1' }), 'quantity_hint')),
    field('token', el('input', { name: 'token', type: 'password', autocomplete: 'off', spellcheck: 'false' }), 'token_hint'),
    live, formError(),
    el('div', { class: 'row' }, el('button', { type: 'submit', class: 'primary', disabled: busy() }, t('save_account'))));
  const sync = () => {
    const data = new FormData(form);
    const balance = data.get('sizing') === 'balance';
    form.querySelector('#fraction-box').hidden = !balance;
    form.querySelector('#quantity-box').hidden = balance;
    const isLive = data.get('mode') === 'live';
    live.hidden = !isLive;
    const account = String(data.get('account') || '').trim().toUpperCase();
    live.querySelector('#live-label').textContent = t('live_phrase', { phrase: 'LIVE ' + (account || '<account>') });
  };
  form.addEventListener('input', sync);
  form.addEventListener('submit', (event) => {
    event.preventDefault();
    const data = new FormData(form);
    const account = String(data.get('account') || '').trim().toUpperCase();
    const sizing = String(data.get('sizing'));
    const token = String(data.get('token') || '').trim();
    const answers = { mode: String(data.get('mode')), account, sizing, token };
    if (!account) return showError(t('required', { field: t('account') }));
    if (sizing === 'balance') {
      const fraction = Number(String(data.get('fraction')).trim());
      if (!(fraction > 0 && fraction <= 1)) return showError(t('bad_fraction'));
      answers.leverage_fraction = String(data.get('fraction')).trim();
    } else {
      const quantity = String(data.get('quantity')).trim();
      if (!/^\d+$/.test(quantity) || +quantity < 1 || +quantity > 10) return showError(t('bad_quantity'));
      answers.quantity = quantity;
    }
    if (!token || /\s/.test(token)) return showError(t('bad_token'));
    if (answers.mode === 'live') {
      const typed = String(data.get('live') || '').trim();
      if (typed !== 'LIVE ' + account) return showError(t('bad_live'));
      answers.live_confirmation = typed;
    }
    form.reset();
    runSetup({ account: answers });
  });
  sync();
  return [el('h2', {}, t('account_title')), el('p', {}, t('account_body')), form];
}

function gatewayForm() {
  const f = state.facts;
  const isLive = f.config && f.config.mode === 'live';
  const vncBox = el('div', { id: 'vnc-box' },
    field('vnc_password', el('input', { name: 'vnc_password', type: 'password', autocomplete: 'new-password', maxlength: '8' }), 'vnc_password_hint'),
    field('vnc_confirm', el('input', { name: 'vnc_confirm', type: 'password', autocomplete: 'new-password', maxlength: '8' })));
  const form = el('form', { novalidate: true },
    field('timezone', el('input', { name: 'timezone', value: 'America/New_York', spellcheck: 'false' }), 'timezone_hint'),
    field('daily', el('input', { name: 'daily', value: '23:45', inputmode: 'numeric' }), 'daily_hint'),
    field('sunday', el('input', { name: 'sunday', value: '12:00', inputmode: 'numeric' }), 'sunday_hint'),
    el('fieldset', {}, el('label', { class: 'inline' }, el('input', { type: 'checkbox', name: 'vnc', checked: true }), t('vnc')),
      el('span', { class: 'hint' }, t('vnc_hint')), vncBox),
    field('username', el('input', { name: 'username', autocomplete: 'off', spellcheck: 'false' })),
    field('password', el('input', { name: 'password', type: 'password', autocomplete: 'off' })),
    isLive ? field('gateway_live', el('input', { name: 'live', autocomplete: 'off', spellcheck: 'false' })) : null,
    formError(),
    el('div', { class: 'row' }, el('button', { type: 'submit', class: 'primary', disabled: busy() }, t('save_gateway'))));
  form.addEventListener('input', () => { vncBox.hidden = !form.elements.vnc.checked; });
  form.addEventListener('submit', (event) => {
    event.preventDefault();
    const data = new FormData(form);
    const time = /^([01]\d|2[0-3]):[0-5]\d$/;
    const answers = {
      timezone: String(data.get('timezone') || '').trim(),
      daily_restart: String(data.get('daily') || '').trim(),
      sunday_restart: String(data.get('sunday') || '').trim(),
      vnc: form.elements.vnc.checked,
      username: String(data.get('username') || ''),
      password: String(data.get('password') || ''),
    };
    if (!answers.timezone) return showError(t('required', { field: t('timezone') }));
    if (!time.test(answers.daily_restart) || !time.test(answers.sunday_restart)) return showError(t('bad_time'));
    if (answers.vnc) {
      const vnc = String(data.get('vnc_password') || '');
      if (!/^[\x21-\x7e]{8}$/.test(vnc) || vnc !== String(data.get('vnc_confirm') || '')) return showError(t('bad_vnc'));
      answers.vnc_password = vnc;
    }
    if (!answers.username) return showError(t('required', { field: t('username') }));
    if (!answers.password) return showError(t('required', { field: t('password') }));
    if (isLive) {
      if (String(data.get('live') || '').trim() !== 'LIVE') return showError(t('bad_live'));
      answers.live_confirmation = 'LIVE';
    }
    form.reset();
    runSetup({ gateway: answers });
  });
  return [el('h2', {}, t('gateway_title')), el('p', {}, t('gateway_body')), form];
}

function loginScreen() {
  const f = state.facts;
  return [
    el('h2', {}, t('login_title')),
    el('p', {}, t('login_body')),
    f.gateway && f.gateway.vnc ? el('p', { class: 'hint' }, t('login_vnc')) : null,
    el('div', { class: 'row' },
      actionButton(t('login_ready'), () => runSetup({ gateway_ready: '' }), 'primary'),
      actionButton(t('tool_gateway_status'), () => command('gateway-status')),
      el('button', { type: 'button', onclick: () => openLogs('gateway') }, t('tool_gateway_logs'))),
  ];
}

function factsList() {
  const f = state.facts;
  const items = [];
  if (f.config) items.push(['fact_mode', f.config.mode], ['fact_size', f.config.size], ['fact_account', f.config.account]);
  items.push(['fact_executor', f.executor_service], ['fact_gateway', f.gateway_service]);
  return el('dl', { class: 'facts' }, items.flatMap(([key, value]) => [el('dt', {}, t(key)), el('dd', {}, value)]));
}

function startScreen() {
  const f = state.facts;
  const phrase = f.config ? f.config.start_phrase : '';
  const input = el('input', { name: 'phrase', autocomplete: 'off', spellcheck: 'false' });
  const form = el('form', { novalidate: true },
    el('label', {}, el('span', {}, t('start_type', { phrase: '' }), el('span', { class: 'phrase' }, phrase)), input),
    formError(),
    el('div', { class: 'row' }, el('button', { type: 'submit', class: 'primary', disabled: busy() }, t('start_button'))));
  form.addEventListener('submit', (event) => {
    event.preventDefault();
    const typed = input.value.trim();
    if (typed !== phrase) return showError(t('start_mismatch'));
    runSetupAction('start', { start_confirmation: typed });
  });
  return [el('h2', {}, t('start_title')), el('p', {}, t('start_body')), factsList(), form];
}

function dashboard() {
  return [
    el('h2', {}, t('dash_title')), el('p', {}, t('dash_body')), factsList(),
    el('div', { class: 'row' },
      actionButton(t('stop_button'), () => { if (confirm(t('stop_confirm'))) command('stop'); }, 'danger')),
  ];
}

// Jobs -------------------------------------------------------------------------
async function runSetup(answers) { return runSetupAction('setup', answers); }

async function runSetupAction(action, answers) {
  try {
    const { job } = await api('/api/run', { action, answers });
    follow(job, action);
  } catch (error) { handleError(error); }
}

async function command(name) { return commandWith({ name }); }

async function commandWith(body) {
  try {
    const { job } = await api('/api/command', body);
    follow(job, body.name);
  } catch (error) { handleError(error); }
}

function handleError(error) {
  if (error.status === 401) { showSessionLost(); return; }
  const box = $('form-error');
  if (box) box.textContent = error.message; else alert(error.message);
}

function showSessionLost() {
  $('screen').replaceChildren(el('h2', {}, t('title')), el('p', { class: 'error' }, t('session_lost')));
  $('steps').replaceChildren();
  $('tools').closest('section').hidden = true;
}

async function follow(id, kind) {
  lastJob = { id, kind };
  const section = $('job');
  section.hidden = false;
  $('job-title').textContent = labelFor(kind);
  $('job-lines').textContent = '';
  $('job-report').replaceChildren();
  $('job-state').textContent = t('running');
  state.job = { id, label: kind, done: false };
  render();
  let next = 0;
  for (;;) {
    let view;
    try { view = await api('/api/jobs/' + id + '?after=' + next); } catch (error) { handleError(error); return; }
    if (view.lines.length) {
      const pre = $('job-lines');
      const atBottom = pre.scrollTop + pre.clientHeight >= pre.scrollHeight - 8;
      pre.textContent += view.lines.join('\n') + '\n';
      if (atBottom) pre.scrollTop = pre.scrollHeight;
    }
    next = view.next;
    if (view.done) { finished(view, kind); return; }
    await new Promise((resolve) => setTimeout(resolve, 700));
  }
}

function labelFor(kind) {
  const keys = { setup: 'continue_title', start: 'start_title', reboot: 'reboot_title', doctor: 'tool_doctor', status: 'tool_status',
    'service-status': 'tool_service', 'gateway-status': 'tool_gateway_status', check: 'tool_check', stop: 'stop_button',
    settings: 'change_sizing', 'discord-link': 'discord_link', 'discord-status': 'discord_status',
    'discord-enable': 'discord_enable', 'discord-unlink': 'discord_unlink', resume: 'resume_button' };
  return t(keys[kind] || kind);
}

function finished(view, kind) {
  const waiting = view.events.some((e) => e.need || e.reboot);
  $('job-state').textContent = view.exit === 0 ? t('finished_ok') : waiting ? t('waiting') : t('finished_fail', { code: view.exit });
  $('job-state').className = 'pill ' + (view.exit === 0 ? 'ok' : waiting ? '' : 'error');
  const report = view.report;
  if (report && Array.isArray(report.problems)) {
    $('job-report').replaceChildren(report.problems.length
      ? el('div', {}, el('p', { class: 'error' }, t('problems')), el('ul', { class: 'problems' }, report.problems.map((p) => el('li', {}, typeof p === 'string' ? p : JSON.stringify(p)))))
      : el('p', { class: 'ok' }, t('no_problems')));
  }
  if (kind === 'status' && report && typeof report === 'object' && 'halt' in report) lastHalt = report.halt || null;
  if (kind === 'discord-link') {
    const line = (($('job-lines').textContent || '').split('\n')).find((l) => l.startsWith('/link code:'));
    if (line) $('job-report').replaceChildren(el('p', {}, t('discord_code')), el('span', { class: 'code-big' }, line));
  }
  if (kind === 'setup') {
    const need = view.events.find((e) => e.need);
    const reboot = view.events.some((e) => e.reboot);
    screen = need ? 'need:' + need.need : reboot ? 'reboot' : view.exit === 0 ? 'start' : 'failed';
  } else if (kind === 'start') {
    screen = view.exit === 0 ? null : 'start';
  } else if (kind === 'reboot') {
    screen = null;
  }
  refresh();
}

async function openLogs(which) {
  try {
    const { job } = await api('/api/logs', { which });
    logsJob = job;
    const section = $('logs');
    section.hidden = false;
    $('logs-title').textContent = t(which === 'gateway' ? 'tool_gateway_logs' : 'tool_logs');
    $('logs-lines').textContent = '';
    let next = 0;
    while (logsJob === job) {
      const view = await api('/api/jobs/' + job + '?after=' + next);
      if (view.lines.length) {
        const pre = $('logs-lines');
        const atBottom = pre.scrollTop + pre.clientHeight >= pre.scrollHeight - 8;
        pre.textContent = (pre.textContent + view.lines.join('\n') + '\n').slice(-200000);
        if (atBottom) pre.scrollTop = pre.scrollHeight;
      }
      next = view.next;
      if (view.done) break;
      await new Promise((resolve) => setTimeout(resolve, 1000));
    }
  } catch (error) { handleError(error); }
}

async function closeLogs() {
  const job = logsJob;
  logsJob = null;
  $('logs').hidden = true;
  if (job) { try { await api('/api/jobs/' + job + '/cancel', {}); } catch (e) { /* already closed */ } }
}

async function refresh() {
  try { state = await api('/api/state'); render(); } catch (error) { if (error.status === 401) showSessionLost(); }
}

async function main() {
  for (const button of document.querySelectorAll('[data-lang]')) {
    button.addEventListener('click', () => {
      lang = button.dataset.lang;
      try { localStorage.setItem('follow-console-lang', lang); } catch (e) { /* storage unavailable */ }
      render(true);
    });
  }
  $('logs-close').addEventListener('click', closeLogs);
  render();
  if (!(await connect())) { showSessionLost(); return; }
  await refresh();
  setInterval(() => { if (!busy()) refresh(); }, 5000);
}

main();
"""
