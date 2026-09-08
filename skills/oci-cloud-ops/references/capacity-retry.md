# Bounded capacity retry

Use this for “抢机”, `Out of host capacity`, or periodic attempts. First identify the operation:

- `start`: start one existing `STOPPED` instance.
- `launch`: create one new instance from a fully reviewed launch JSON.

Do not call both in the same retry job.

## Why the provided script is required

`scripts/oci_capacity_retry.py` provides:

- a minimum 60-second interval;
- an explicit maximum attempt count;
- a state file and exclusive lock to prevent overlapping jobs;
- request-file hashing to reject mid-run launch-template changes;
- an OCI retry token preserved across ambiguous failures and rotated only after a definite capacity rejection;
- success and fatal-error sentinels so later scheduler invocations become no-ops;
- distinct handling for capacity, throttling/transport ambiguity, quota/limit, IAM, and invalid parameters;
- no automatic deletion, AD/shape switching, or cost-changing fallback.

The script never reads private-key contents and never logs launch JSON or User Data. It rejects launch templates containing PEM private keys.

## Prepare a launch retry

Generate a complete command JSON, fill it, then review every field:

```bash
oci compute instance launch --generate-full-command-json-input > /secure/path/launch.json
chmod 600 /secure/path/launch.json
```

Include an SSH public key. If root password login was explicitly requested, generate hashed cloud-init with `scripts/render_root_cloud_init.py`; do not put plaintext credentials in the JSON.

Dry-run the job:

```bash
python3 scripts/oci_capacity_retry.py launch \
  --profile PROFILE \
  --region REGION \
  --request-file /secure/path/launch.json \
  --state-file /secure/path/retry-state.json \
  --max-attempts 360 \
  --dry-run
```

Run once per scheduler tick:

```bash
python3 scripts/oci_capacity_retry.py launch \
  --profile PROFILE \
  --region REGION \
  --request-file /secure/path/launch.json \
  --state-file /secure/path/retry-state.json \
  --max-attempts 360 \
  --once
```

Or run a bounded foreground loop at one request per minute:

```bash
python3 scripts/oci_capacity_retry.py launch \
  --profile PROFILE \
  --region REGION \
  --request-file /secure/path/launch.json \
  --state-file /secure/path/retry-state.json \
  --max-attempts 360 \
  --interval-seconds 60
```

## Existing-instance start retry

```bash
python3 scripts/oci_capacity_retry.py start \
  --profile PROFILE \
  --region REGION \
  --instance-id INSTANCE_OCID \
  --state-file /secure/path/start-state.json \
  --max-attempts 120 \
  --interval-seconds 60
```

The script checks state before sending `START`. `RUNNING` is success; `STARTING` is observed without sending another start; lifecycle states other than stopped/startable are fatal.

## Scheduling

Oracle documents that the Console has no built-in schedule and suggests OCI CLI plus an OS scheduler. On macOS prefer a user LaunchAgent with `StartInterval = 60`; on Linux use systemd timer or cron. Invoke the script with `--once`. Keep the state file on persistent local storage and send stdout/stderr to a protected log.

On macOS, render a LaunchAgent instead of hand-editing XML:

```bash
python scripts/render_macos_launchagent.py start \
  --label com.example.oci-capacity-retry \
  --profile PROFILE \
  --instance-id INSTANCE_OCID \
  --state-file /secure/path/state.json \
  --stdout /secure/path/stdout.log \
  --stderr /secure/path/stderr.log \
  --output "$HOME/Library/LaunchAgents/com.example.oci-capacity-retry.plist"
launchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/com.example.oci-capacity-retry.plist"
```

Stop and remove the paired job with `launchctl bootout "gui/$(id -u)/com.example.oci-capacity-retry"`, then remove only that exact plist after confirming it is unloaded. The renderer enforces a minimum 60-second interval and always invokes one bounded `--once` tick.

Do not install or remove a scheduler without authorization. On install, always provide the paired stop/uninstall command. A one-minute interval is supported by this Skill, but Oracle's own capacity guidance says to wait a few minutes; if throttled, stop or increase the interval rather than multiplying concurrent jobs.

Official sources:

- [Automatic start/stop workaround](https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/howto-start-stop-instance.htm)
- [Out of Host Capacity](https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/troubleshooting-out-of-host-capacity.htm)
- [OCI retry behavior](https://docs.oracle.com/en-us/iaas/tools/python/latest/sdk_behaviors/retries.html)
- [REST retry tokens and throttling](https://docs.oracle.com/en-us/iaas/Content/API/Concepts/usingapi.htm)

## Stop conditions and final verification

Stop immediately on accepted launch/start, quota or compartment-quota failure, IAM failure, invalid image/shape/subnet, exhausted attempts, changed request hash, or manual interruption.

After success, independently read the new/current instance and verify lifecycle, shape, image, boot volume, VNIC/public IP, network rules, cloud-init, SSH key login, and root password login only if requested. Accepted API response is not the same as usable SSH service.
