# Instance, storage, network, and SSH operations

Read the relevant section only. Re-read the target immediately before mutation and use lifecycle-state preconditions where supported.

## Power actions

Use the official action operation:

```bash
oci --profile PROFILE compute instance action --instance-id INSTANCE_OCID --action START
oci --profile PROFILE compute instance action --instance-id INSTANCE_OCID --action SOFTSTOP
oci --profile PROFILE compute instance action --instance-id INSTANCE_OCID --action SOFTRESET
```

Prefer graceful `SOFTSTOP`/`SOFTRESET` when the OS responds. Explain that forced `STOP`/`RESET` can corrupt in-flight writes. After the request, wait for and re-read the desired state.

Official sources: [Power actions](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/compute/instance/action.html) and [Starting an instance](https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/restartinginstance-start-instance.htm).

## Reinstall or rebuild

First clarify whether the goal is a clean OS, a compatible image refresh, data recovery, or shape change.

- **Boot-volume replacement:** supported for compatible Linux images/volumes. Confirm distribution compatibility, same-AD constraints where applicable, IAM, and preservation of the previous boot volume. This is the closest supported in-place reinstall path.
- **Terminate and recreate:** required when changing to an incompatible OS/image or when a clean resource boundary is desired. Preserve boot/data volumes and backups until the replacement is verified.

Never call a reboot a reinstall. Never terminate first when parallel replacement is possible and the user has not authorized data loss.

Official source: [Replacing a Boot Volume](https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/replacingbootvolume.htm).

## Create an instance

Generate and review a complete launch JSON rather than building an opaque one-line command:

```bash
oci compute instance launch --generate-full-command-json-input > launch.json
oci --profile PROFILE --region REGION compute instance launch --from-json file://ABSOLUTE_LAUNCH_JSON
```

Verify compartment, AD, shape config, image architecture, boot volume, subnet, public-IP choice, NSGs, SSH public key, User Data, tags, and estimated cost/free eligibility. Do not put a private SSH key in metadata. Use a supported retry token on the actual create request.

Official source: [OCI CLI launch](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/compute/instance/launch.html).

## Public IP and network changes

A public IP is assigned to a private-IP object on a VNIC. Resolve the chain before deleting or assigning anything:

```text
instance -> VNIC attachment -> VNIC -> primary private IP -> public IP object
```

Before releasing an ephemeral address, record the old public-IP OCID, private-IP OCID, VNIC, subnet, route table, NSGs, and security lists. Release-and-reallocate is not reversible; the old address may not return. Do not run connectivity tests when the user explicitly says they will test.

For rule changes, prefer a narrowly scoped NSG over broadening a whole subnet security list. Check all three control planes: NSGs, subnet security lists, and the guest OS firewall. Restrict SSH to the authorized management CIDR whenever feasible. Never add all-protocol `0.0.0.0/0` as a convenience fix.

An explicitly declared firewall posture is an authorization boundary. If the user states that broad ingress or open ports are intentional and asks not to change them, preserve that posture and report the risk instead of silently normalizing it to least privilege. Make only the exact rule change needed for the requested service, verify it once, and do not repeatedly tighten or reopen the same path.

Official sources: [Public IP Addresses](https://docs.oracle.com/en-us/iaas/Content/Network/Tasks/managingpublicIPs.htm) and [NSGs](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/network/nsg.html).

## SSH keys, password login, and root access

OCI stores the public SSH key in instance metadata; it cannot reconstruct or download the matching private key. For a new instance, always retain a locally generated SSH key as recovery access.

Password/root access is opt-in and high risk. If explicitly requested for a new Linux instance:

1. Run `scripts/render_root_cloud_init.py --output /secure/path/root-login.yaml` interactively. It stores a SHA-512 hash, not the plaintext password.
2. Keep `--ssh-authorized-keys-file` on the launch.
3. Pass the cloud-config with `--user-data-file`.
4. Restrict TCP/22 at the NSG/security-list layer before exposing password login.
5. Wait for cloud-init completion and verify effective values with `sshd -T`.
6. Keep the first key-based session open while testing a second, fresh `root + password` session. Do not print or log the password.

The generated file uses an early SSH drop-in because OpenSSH generally uses the first obtained value and vendor/cloud-init fragments may otherwise win. Validate with the actual image; do not assume Ubuntu, Oracle Linux, and custom images share service names or include order.

### Change a password or enable password SSH on an existing instance

If SSH key access still works, use that session as the recovery channel:

1. Resolve the actual login user and read `sshd -T`; distinguish “change an existing password” from “enable password authentication” and “allow root password login”.
2. Restrict TCP/22 to the authorized management CIDR before enabling password authentication.
3. Keep the current key-authenticated session open. Back up only the SSH drop-in that will be changed and record its mode/owner.
4. Change the chosen account password interactively with `sudo passwd USER`. Do not place the password in argv, shell history, a here-document, Run Command, logs, or a temporary file.
5. If password SSH must be enabled, create an early, narrowly scoped `sshd_config.d` drop-in. Add `PermitRootLogin yes` only when root login was explicitly requested; ordinary-user password login does not require it.
6. Run `sudo sshd -t`, reload/restart the correct SSH service, then verify effective values again with `sudo sshd -T`.
7. Open a second external SSH session using the requested account and password. Do not close the original key session until this succeeds.
8. On failure, restore the saved drop-in from the still-open session, validate with `sshd -t`, and reload SSH. Report the rollback.

If no key, console, or agent channel works, do not “fix” access by replacing the instance first. Choose serial-console recovery, an offline boot-volume repair, or parallel replacement according to the user's data-retention goal. Any offline password hash remains sensitive and must not be printed.

For an existing inaccessible instance, prefer SSH key/console recovery. Run Command depends on Oracle Cloud Agent and the plugin, has image and permission constraints, and Oracle explicitly warns against sending secrets in plaintext. Do not use Run Command to transmit a root password. Use Vault/Object Storage or an offline boot-volume repair if a secret-bearing recovery is unavoidable.

Official sources:

- [Running Commands on an Instance](https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/runningcommands.htm)
- [Oracle Cloud Agent](https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/manage-plugins.htm)
- [Instance Metadata](https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/gettingmetadata.htm)
- [cloud-init password module](https://docs.cloud-init.io/topics/modules.html#set-passwords)

## Paired-operation audit

Before completion, classify every related location or resource:

- Changed and verified.
- Related but intentionally unchanged, with reason.
- Still requiring action.

At minimum pair create/terminate, attach/detach, allocate/release, allow/deny, password enable/disable, and scheduler install/uninstall.
