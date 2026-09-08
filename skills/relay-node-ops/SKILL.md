---
name: relay-node-ops
description: "Prepare and verify Linux relay nodes using the user's existing BBR, GOST, Brook, iptables, or V2Ray installers, and safely deploy an isolated Shadowsocks-libev server when requested. Use on Ubuntu, Debian, CentOS, Rocky, AlmaLinux, or other RHEL-compatible servers, including targets that cannot access GitHub directly."
---

# Relay Node Ops

Use the existing installers; do not rebuild their functions. The controller can be macOS, but the deployment target must be Linux.

## Role selection

For each server, choose one main role:

- `gost`, `brook`, or `iptables`: forwarding methods, normally three choose one.
- `v2ray`: a node role, normally separate from forwarding.
- `ss-server`: an isolated Shadowsocks-libev server role. Read [shadowsocks-libev.md](references/shadowsocks-libev.md) before deploying it.
- `bbr`: optional acceleration before the selected main role.

Do not install multiple forwarding methods unless the user explicitly asks.

## Fast workflow

1. SSH to the target and run `scripts/linux_preflight.sh`. Support Ubuntu/Debian and CentOS/RHEL/Rocky/AlmaLinux families; stop on unsupported systems.
2. Confirm the requested role and collect only the inputs that its installer needs: listen port, destination IP/domain and port, protocol, or V2Ray transport details.
3. Run `scripts/prepare_installer.sh ROLE` on the Linux target. It installs only basic download dependencies when requested, downloads the existing installer into a cache, checks shell syntax, prints its SHA-256, and does not execute it by default.
4. If direct GitHub access fails, use `scripts/prepare_installer.sh ROLE --china-source`. This uses the mainland-tested bootstrap route and adapts the installer's later GitHub requests. Read [china-source-validation.md](references/china-source-validation.md) for the measured route and fallback order. If both public routes fail, download on the controller, SCP the reviewed file, and combine `--local-script` with `--china-source`.
5. Review the printed source, final URL, SHA-256, and warnings from [security-review.md](references/security-review.md). Execute with `--run --confirm`; interact with the installer's own menu through a PTY.
6. Verify the actual result: kernel BBR state, process/service, exact listener, end-to-end forwarding or real client connection, and restart persistence. Use `scripts/wait_for_listener.sh SERVICE PORT` instead of asserting a listener immediately after `systemctl start`.
7. If the user reserves client acceptance testing for themselves, stop after server, listener, persistence, and authorized hop checks. Do not install a temporary client package or create a client config on a relay host.
8. Return a short maintenance card: Linux family, role, installer URL/hash, ports/destination, service/config path discovered after install, status/log command, and the installer's uninstall path. Do not expose passwords, keys, or client artifacts unless the user explicitly requested that exact artifact in the current task.

## Commands

```bash
# Environment only
scripts/linux_preflight.sh

# Prepare without executing
sudo scripts/prepare_installer.sh gost

# Mainland target or direct GitHub failure
sudo scripts/prepare_installer.sh gost --china-source

# Run after review
sudo scripts/prepare_installer.sh gost --run --confirm

# GitHub-blocked target: copy a reviewed script from the controller first
sudo scripts/prepare_installer.sh gost \
  --local-script /tmp/gost.sh --china-source --run --confirm
```

Available roles and sources are in [script-catalog.md](references/script-catalog.md).

## Operating boundaries

- Treat the scripts' own menus and uninstall functions as the source of truth; do not add a parallel service-management layer.
- Use a PTY for interactive installers. Do not try to automate menu numbers until the current downloaded version has been inspected.
- Back up current firewall rules and record existing listeners before GOST/Brook/iptables changes.
- BBR scripts may replace kernels or reboot. Ask for explicit confirmation immediately before that menu action.
- In GOST China mode, answer `n` when its old menu asks whether to use the built-in mainland mirror. That Aliyun OSS endpoint failed all mainland probes on 2026-08-19; the prepared copy already routes GitHub downloads through the tested adapter.
- Never alter SSH access, cloud security rules, or unrelated firewall policy as an incidental step.
- Test changes on the authorized Linux machine, not on the macOS controller.
- Preserve a user-declared open-port or firewall posture. Report the risk, but do not silently replace it with a stricter policy.
- For known failures and their reusable fixes, read [troubleshooting.md](references/troubleshooting.md).
