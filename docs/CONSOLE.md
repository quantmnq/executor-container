# Setup console (preview)

English | [简体中文](CONSOLE.zh-CN.md)

The setup console is a private page in your browser for the same steps as
`./follow-stack setup`: Docker and startup, the verified executor image, account and
sizing, Gateway login, phone approval, the readiness check and an explicit start. It
also shows status and logs, stops following, and changes sizing and Discord
notifications later. It runs the same code as the
terminal wizard, so every check, typed confirmation and saved file is the same.

It needs the combined container kit (`follow-stack-…`) on Ubuntu 24.04 ARM64 and a
working SSH connection to the VM. Oracle signup and IBKR account preparation still
follow [SETUP.md](SETUP.md) and [IBKR_ACCOUNT_SETUP.md](IBKR_ACCOUNT_SETUP.md).

## Open the console

On your own computer, run one command. It connects to the VM, forwards the console
and recovery-desktop ports through SSH, and starts the console:

```bash
ssh -i ./auto-quant.key -t -L 8765:127.0.0.1:8765 -L 5901:127.0.0.1:5901 ubuntu@YOUR_OCI_PUBLIC_IP './follow-stack-VERSION-ubuntu24.04-arm64-cp312/follow-stack console'
```

Replace the key path, IP address and `VERSION` with yours. The command prints a
private link such as `http://127.0.0.1:8765/#token=…`. Open it in your browser on the
same computer. Keep the SSH window open while you use the page.

Choose **Continue setup**. The console checks the VM and stops at the first step that
needs you. Fill in each form and follow the instructions. Choose **中文** at the top
for Chinese.

## What stays the same

- Setup never starts trading. **Start following** appears only after the readiness
  check passes, and you must type the exact phrase shown, such as
  `START PAPER BALANCE 0.5`.
- Live mode needs the same typed confirmations as the terminal wizard.
- Docker installation and user-service lingering use sudo only after you approve
  them. Docker changes then need one VM restart; the console offers a button. After
  the restart, run the same SSH command again and open the new link.
- **Stop following** does not close positions or cancel broker orders. Stop only
  while flat unless you are handling the position yourself.

## Change settings later

The **Settings** card appears once your account is saved. Sizing and Discord changes
need a stopped executor, so while following is running the card shows only Advanced
recovery.

- **Change sizing**: choose balance sizing with a leverage fraction, or a fixed MNQ or
  NQ size. Add an approximate NQ price to see a size preview at your IBKR
  NetLiquidation with example weights. The account must be flat, with no halt and no
  working orders, and Gateway must be logged in. If the change is refused, the old
  settings are kept. The new size takes effect at the next start.
- **Discord notifications (optional)**: read what is shared, type `LINK` and choose
  **Get pairing code**. Send the shown `/link code:…` command to AQ Bot in your
  provider's Auto Quant Discord server. After the test DM arrives, choose **Enable
  notifications**. See [DISCORD.md](DISCORD.md).
- **Advanced recovery**: **Executor status** shows whether the executor is halted.
  Request halt recovery only after inspecting the account, by typing `RESUME`. The
  running executor then takes ownership of the broker's current position and aligns
  it with the latest target, which may close it.

After a sizing or Discord change, run the readiness check again before starting.

## Privacy

- The console listens on 127.0.0.1 on the VM only. You reach it through your SSH
  connection; no OCI security-list rule or firewall change is needed.
- Each printed link works once and becomes a private browser session. Do not share
  the link.
- Type your relay token, IBKR username and password, and the recovery-desktop
  password only into the console page. They are saved to the same private files as
  the terminal wizard and are never shown again or logged.
- An AI assistant may start the console and read its progress, but must never fill
  in credential fields or receive these values in chat.

## Close and reopen

Close the console with Ctrl+C or by closing the SSH window. It also closes after 30
idle minutes. Gateway and the executor keep their current state. Run the SSH command
again to reopen it; setup resumes from saved steps.

## Troubleshooting

| Problem | What to do |
| --- | --- |
| The page does not load | You connected without `-L 8765:127.0.0.1:8765`. Close the SSH window and use the command above |
| "This page is not connected" | The link was already used. Press Ctrl+C in the SSH window, run the command again and open the new link |
| Port 8765 is in use | Another console is open, or a local program uses the port. Add `--port 8766` after `console` and forward `8766` instead |
| A Gateway dialog needs attention | Open your VNC viewer at `localhost:5901` (TigerVNC: `localhost::5901`) and enter the recovery-desktop password |
| A step fails | Read the output under the form. Fix what it describes, then choose **Continue setup**. Saved settings are kept |

The terminal wizard remains available at any time: `./follow-stack setup`. See
[CONTAINER_SETUP.md](CONTAINER_SETUP.md) for maintenance and recovery.
