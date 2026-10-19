# Auto Quant customer installation

These instructions apply to the extracted customer package, not source development.
Read `docs/AGENT_SETUP.md` (or `docs/AGENT_SETUP.zh-CN.md`) and the matching
`docs/SETUP.md` before setup. Use the customer's language and the supplied scripts.
For a combined kit (`RELEASE.json` contains `executor_image`), use
`docs/SETUP.md` plus `docs/CONTAINER_SETUP.md` (or their Chinese counterparts)
and `./follow-stack setup`
instead of the native installation steps. No host venv or Java installation is needed.
A native-only kit uses `docs/SETUP_NATIVE.md` or its Chinese counterpart. The
container wizard configures API settings; screenshots are for manual inspection
when needed, not a mandatory reason to change settings.

- Inspect existing installation and service state; resume from verified checkpoints.
- Run installation on Ubuntu 24.04 ARM64 with Python 3.12, not on the laptop.
- Hand private-input prompts to the customer's own terminal. Never ask for secrets
  in chat or read/display credential files. Customer handles phone/Discord consent.
- Keep a private, secret-free progress note as described in the agent guide.
- At the Gateway API-settings checkpoint, show both bundled Gateway screenshots
  using a customer-visible preview or file link before the corresponding clicks.
  Follow the display guidance in `docs/AGENT_SETUP.md`.
- For Discord linking, show the bundled #bot-setup screenshot before the customer
  submits AQ Bot's `/link`. Explain that the example code is a placeholder; the
  customer enters their own code directly in Discord.
- Start with paper trading. Get explicit agreement to the verified mode, root and
  quantity before the first trading start. Do not automate LIVE confirmations.
- Do not stop active trading, reset journals, change risk checks
  or operate provider services to complete installation.
- Report actual results and unfinished steps; do not claim unobserved trading tests.
