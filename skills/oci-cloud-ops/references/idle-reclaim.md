# Always Free idle-reclaim guard

Use this reference when the user asks about low-activity reclamation, 保活, 防回收, idle protection, or a controlled resource-occupancy service.

## Current Oracle policy

Oracle's current Always Free documentation says idle Always Free compute instances may be reclaimed. Oracle deems an instance idle when, during a 7-day period, all applicable conditions are true:

- CPU utilization at the 95th percentile is below 20%.
- Network utilization is below 20%.
- Memory utilization is below 20% for A1 shapes.

The word is “may”; the policy does not promise an exact reclaim time or guarantee that crossing one observed metric threshold prevents reclamation. Oracle does not document enough detail to reproduce its internal network-utilization classification. Refresh the official page immediately before advising or installing:

- [Always Free Resources — Idle Compute Instances](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm)
- [Compute Instance Metrics](https://docs.oracle.com/en-us/iaas/Content/Compute/References/computemetrics.htm)

Do not confuse the 20% reclaim criterion with a monthly traffic quota:

- E2 Micro is documented as up to 50 Mbps to the public internet and up to 480 Mbps for private, same-region, or DRG traffic.
- A1 Flex is documented as up to 1 Gbps per OCPU, scaling with OCPU count, with a 40 Gbps shape maximum. This is a VNIC/shape ceiling, not a guaranteed speed to every internet destination.
- Always Free includes 10 TB per month of outbound data at the tenancy level under the current offer. That allowance is separate from the shape's instantaneous bandwidth and from the idle-reclaim percentage.

Because the idle definition requires every applicable condition to remain below threshold, the E2 guard deliberately affects CPU only. Do not create synthetic network traffic merely to change the network criterion.

- [Compute Shapes](https://docs.oracle.com/en-us/iaas/Content/Compute/References/computeshapes.htm)
- [Always Free Resources — Outbound Data Transfer](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm)

## Scope and warning

`scripts/oracle_idle_guard.py` is an explicit opt-in resource occupancy process. It targets bounded CPU and, for A1 only, memory utilization. It performs no network activity, does not call OCI APIs, and needs no OCI key, instance principal, or cloud credentials. It is not Oracle software or an Oracle-approved exemption from reclamation.

Before installing, state all of the following:

- It intentionally consumes otherwise idle resources and should not replace a real workload.
- It may affect power use, thermals, performance, monitoring, and capacity available to applications.
- It does not guarantee that Oracle will retain the instance.
- The user remains responsible for their Oracle agreement and current service policies.
- Backups and a tested rebuild path remain necessary.

Do not deploy a third-party `curl | bash` keepalive installer, bandwidth generator, speed-test loop, cryptocurrency miner, or unbounded CPU/memory loop. Do not install this guard unless the user explicitly chose controlled occupancy after seeing the warning.

## Reviewed community approaches

The local implementation is independent; no third-party installer or source file is vendored. These public projects were reviewed for design ideas only:

- [Codycody31/Prevent-OCI-Deletion-for-being-idle](https://github.com/Codycody31/Prevent-OCI-Deletion-for-being-idle) (MIT): useful precedent for checking total CPU before work and preventing duplicate managers, but its cron/permanent-manager model, multi-worker bursts, broad process killing, and incomplete uninstall are not used.
- [spiritLHLS/Oracle-server-keep-alive-script](https://github.com/spiritLHLS/Oracle-server-keep-alive-script) (MIT): useful precedent for calculating a memory gap from total system use and cleaning exact cron blocks, but fixed CPU duty, delayed memory release, bandwidth tests, BOINC, remote installers, and root-managed paths are not used.
- [Drag-NDrop/OCIScripts](https://github.com/Drag-NDrop/OCIScripts): no detected license, so its code is not copied or adapted; its stale CPU sample and unbounded busy-loop patterns are also unsafe.

Keep the resulting invariants: local feedback rather than a fixed worker count, in-flight workload avoidance rather than only a pre-check, no network mode, no OCI credentials, systemd cgroup limits, deterministic managed files, and fail-closed uninstall.

## Behavior

- The controller reads local Linux `/proc/stat`; it never needs Oracle Monitoring data.
- It estimates non-guard CPU use and immediately reduces its duty cycle as real workload rises.
- Targets are hard-capped at 30%. One guard thread can consume at most one CPU core; systemd also applies low CPU/IO weights and `Nice=19`.
- A1 memory target defaults to 25%, is hard-capped at 30%, grows in small steps, and shrinks as non-guard memory use rises.
- A1 mode is memory-only: its CPU target is 0%, while the controller continuously keeps total system memory near 25%. Existing application memory counts toward the target, and the guard releases its buffer as application use rises. Oracle's memory condition applies only to A1, so extra CPU occupancy is unnecessary.
- E2 mode is CPU-only: memory occupancy is 0%, and its fixed service profile targets 25% total CPU for at most 15 minutes every 2 hours. With one-minute samples this places about 12.5% of samples above the 20% threshold while averaging about 3.1% full-machine CPU before workload avoidance. `CPUQuota=50%` is an additional ceiling on the x86 micro VM.
- Both fixed shape profiles reject custom targets so status checks can detect configuration drift.
- systemd gives the process a 35% memory hard limit and an OOM score that makes it the preferred process to kill under pressure.
- `PrivateNetwork=yes` and `RestrictAddressFamilies=AF_UNIX` prevent internet or VCN traffic from the service.

Oracle samples Compute metrics every ten seconds and emits six samples per minute, but it does not document enough of the reclaim classifier to prove that a local schedule will prevent reclamation. The 25%/15-minute/2-hour E2 profile is therefore best effort. Its 3.1% figure is a time-weighted average; P95 is expected to fall in the high 12.5% sample set and therefore be near 25% under one-minute sampling. OCI Monitoring can be inspected separately from an authenticated administrator workstation, but the guard must not receive or depend on OCI credentials.

## Install on a Linux instance

First inspect the exact plan. For A1:

```bash
sudo python3 scripts/install_linux_idle_guard.py install \
  --shape a1 \
  --dry-run
```

For E2 Micro, which uses CPU control only:

```bash
sudo python3 scripts/install_linux_idle_guard.py install \
  --shape e2 \
  --dry-run
```

After the user confirms the target instance, shape, load impact, and rollback, remove `--dry-run`. A1 enables `oracle-idle-guard.service`; E2 enables `oracle-idle-guard.timer`, which invokes the bounded service pulse.

The installer writes only:

- `/usr/local/lib/oracle-idle-guard/oracle_idle_guard.py`
- `/etc/systemd/system/oracle-idle-guard.service`
- `/etc/systemd/system/oracle-idle-guard.timer` (E2 only)

It refuses to overwrite a different existing file or a symlink. It requires Linux, Python 3.8+, systemd, and root for a live install.

## Verify

```bash
sudo python3 scripts/install_linux_idle_guard.py status
systemctl show oracle-idle-guard.service \
  -p ActiveState -p SubState -p CPUQuotaPerSecUSec -p MemoryHigh -p MemoryMax
systemctl list-timers oracle-idle-guard.timer --no-pager
journalctl -u oracle-idle-guard.service --since '15 minutes ago' --no-pager
```

Verify that logs report `network_activity=disabled`, the service stays within its cgroup limits, real application latency remains acceptable, and OCI Monitoring continues to receive metrics. Recheck the 7-day charts; a short local sample is not sufficient verification.

## Uninstall and rollback

```bash
sudo python3 scripts/install_linux_idle_guard.py uninstall --dry-run
sudo python3 scripts/install_linux_idle_guard.py uninstall
```

Then verify both units no longer exist and that the exact managed files above are absent. Uninstalling the guard does not touch the application, instance, boot volume, network, SSH configuration, or OCI resources.

## Data protection remains mandatory

Treat the guard as a best-effort occupancy control, not a retention guarantee. Before relying on an Always Free instance, identify application data, create an appropriate boot/block-volume or application-level backup, store recovery material outside the instance, and test a rebuild. Backup creation, retention, and storage cost require separate authorization.
