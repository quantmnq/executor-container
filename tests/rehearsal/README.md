# Disposable Ubuntu installation rehearsal

This harness exercises the packaged wizard on a fresh Ubuntu 24.04 ARM64 guest,
without an IBKR login, real relay token or orders. The host pilot keeps running.
An emulated guest tests installation behavior, not trading latency or customer
hardware performance. Only the guest is rebooted.

Build the helper image from this directory's Dockerfile with
`--build-arg REHEARSAL_UID="$(id -u)"` so its SSH client can resolve the mapped UID.
Download a dated official
[Ubuntu ARM64 cloud image](https://cloud-images.ubuntu.com/noble/) and verify its
SHA256 against the same dated directory's SHA256SUMS. Keep the source URL/hash in
the local validation record. Create a private directory containing the image, a
qcow2 overlay with 12 GiB virtual space, a new disposable SSH key, and a cloud-init
seed. Seed only user `ubuntu`, its public key, passwordless sudo, hostname
`follow-rehearsal`, and disabled password/root SSH login. Do not copy customer files.

Use QEMU's `virt` machine, `-cpu cortex-a72 -accel tcg,thread=single,tb-size=128 -smp 1 -m 1536`,
`-icount shift=3,sleep=on -rtc clock=vm -device virtio-rng-pci`,
`-bios /usr/share/AAVMF/AAVMF_CODE.fd`, virtio disks for overlay and seed, and:

```text
-netdev user,id=net0,hostfwd=tcp::2222-:22
-device virtio-net-pci,netdev=net0,romfile=
-nographic -monitor none
```

Run this helper in Docker as your UID/GID with `--cap-drop ALL`,
`--security-opt no-new-privileges`, a CPU limit of 0.5–0.75, `--memory 3g`, and only the
private fixture directory mounted at `/vm`. Publish only `127.0.0.1:22292:2222`.
No privileged mode, host devices, host Docker socket or host service files are
mounted. The empty ROM filename disables unneeded network boot firmware.
Instruction-counted virtual time avoids device deadlines expiring while this
resource-limited software emulator is busy; this is not a real-time clock test.
See [QEMU invocation](https://www.qemu.org/docs/master/system/invocation.html).
Budget memory for QEMU's translation cache and guest disk cache as well as guest
RAM; an earlier 2304 MiB emulator cap was insufficient during package installation.

Wait for `cloud-init status` to finish. Record the OS, architecture and absence of
Docker. Copy the customer archive and its checksum over SSH, verify, and extract
into a permanent guest directory. Use a separate known-hosts file. Then run:

```bash
python3.12 tests/rehearsal/drive-wizard.py \
  --identity /absolute/private/guest-key \
  --known-hosts /absolute/private/known-hosts \
  --container follow-rehearsal-20261017 \
  --release /home/ubuntu/follow-stack-VERSION-ubuntu24.04-arm64-cp312 \
  --phase decline --log /absolute/private/decline.log
```

Repeat with `--phase docker` to accept Docker installation. Confirm the wizard
exits asking for a reboot. Reboot **only this guest** over its SSH connection, then
record its changed boot ID. Check `follow-stack doctor`: Docker must work in both
the new shell and user manager without ACL repairs, and lingering must be enabled.

Once guest Docker creates its default bridge, the host-published SSH route can
conflict with the outer Docker network. Use SSH/scp via `docker exec` inside the
QEMU helper, targeting `127.0.0.1:2222`. The driver does this with `--container`.
Use the same verified host key (`HostKeyAlias=[127.0.0.1]:22292` when using the
initial published port's known-hosts entry). This keeps the guest installer unchanged.

Run phases `configure`, then `resume`. These enter a dummy paper account and token,
then interrupt setup at step 4 before IBKR credentials or login. Compare hashes of
the saved config, token and journal before/after resume; inspect private file modes,
SQLite integrity and the stopped/disabled executor service. Gateway must remain
stopped. The script fails if its expected prompts or cancellation exit code differ.

Do not call this an authenticated onboarding test: mobile approval, account access,
real quotes, a complete upgrade against an authenticated account, and scheduled
re-authentication require separate evidence. `test_maintenance.py` exercises
release-switch transactions with fake broker/service operations, including a real
SIGKILL of the maintenance controller and preservation of newer journal history.

After the two setup phases, copy and extract a separately retained compatible kit
into another guest directory. Run `maintenance-fixture.py --old OLD --new NEW
--report REPORT.json` inside this disposable guest. It verifies the dummy token
and hostname before setting up a fixture Gateway service/volume. Docker, image
loading, systemd and backups are real; only the flat-account probe is simulated.
It tests upgrade and rollback while retaining new journal entries, a halt, private
configuration and a volume sentinel. No service is started. This does not replace
authenticated maintenance acceptance.

When finished, remove only this named rehearsal container. Retain the private
evidence if needed; no changes to the host's active Gateway or executor are needed.
