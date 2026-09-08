# Proxmox VE Operations and Safety

## Universal Preflight

Before a mutation, capture:

- installed PVE version and API schema;
- exact cluster, node, VMID or CTID, storage, and bridge identifiers;
- cluster quorum and target object's owner node;
- current status and relevant configuration;
- active tasks that could conflict;
- available backup, snapshot, console, and out-of-band recovery access;
- expected downtime, blast radius, rollback trigger, and rollback action.

If the active identity is `root@pam` or another administrator, say so in the permission prompt. Root use is supported; the warning exists to prevent acting on the wrong node, guest, storage, or cluster object.

Re-read the target immediately before execution. Do not retry an ambiguous timeout until task history proves the first request did not take effect.

## Risk Matrix

| Domain | Read-only discovery | Mutations requiring explicit approval | Minimum recovery preparation |
| --- | --- | --- | --- |
| Cluster and quorum | status, members, resources, tasks | join/remove node, corosync, quorum changes | healthy quorum, config backup, console on affected nodes |
| Nodes | status, services, disks, tasks | reboot, shutdown, service or time changes | workload evacuation plan and out-of-band console |
| QEMU and LXC | status, config, pending config, agent data | stop/reset/delete, hardware change, clone, move, resize | current backup/snapshot as appropriate and exact guest ID |
| Storage and disks | status, content, usage, health | create/remove storage, wipe, detach, move, resize | dependency inventory, backup, restore destination and capacity |
| Snapshots and backups | list, status, job/task logs | rollback, delete, restore, prune | restore plan, retention impact, target collision check |
| Migration, HA, replication | state, groups, schedules, logs | migrate, add/remove HA, failover, replication changes | capacity, shared-storage/network checks, rollback owner node |
| Network, SDN, firewall | bridges, bonds, VLANs, rules, pending config | apply/reload/change addresses, routes, rules, zones | second session, console, config backup, timed rollback path |
| Users and permissions | users, realms, roles, ACLs, token metadata | create/delete/change ACL, token, realm, 2FA, cert | independent admin access and tested rollback identity |
| Updates and boot | repositories, package versions, kernel, boot state | repository changes, upgrade, kernel/bootloader, reboot | release notes, backups, compatible cluster order, console |

## Permission Prompt

Before any write, present a compact prompt in this shape:

```text
Privileged identity: root@pam (or scoped token name)
Target: cluster/node/VMID/CTID/storage/bridge
Operation: exact API method and path or CLI command
Impact: restart/downtime/data/network/security effect
Rollback: exact recovery action or "not reversible"
Proceed with this write operation?
```

For delete, wipe, snapshot rollback, restore-overwrite, cluster membership, management network, or permission changes, add a separate line beginning with `DESTRUCTIVE OR LOCKOUT RISK:`.

## Guest Lifecycle

- Distinguish graceful shutdown from stop/reset. Prefer graceful actions when the guest is responsive.
- Check HA state before manual power or migration actions; HA may counteract an unmanaged operation.
- For config changes, inspect current and pending config and identify whether a reboot is required.
- Do not delete a VM or container until its identity, disks, backup state, replication, HA membership, and protection flag are verified.
- Treat `qm destroy`, `pct destroy`, and equivalent DELETE endpoints as destructive and target-specific.

## Storage, Disk, Snapshot, and Backup

- Confirm storage type, shared/local semantics, free space, guest dependencies, and replication or backup impact.
- Disk resize is generally one-way at the virtual device layer. Do not present a filesystem shrink as a routine rollback.
- A snapshot is not automatically an independent backup. Verify where guest disks live and whether the storage supports the requested snapshot semantics.
- Snapshot rollback overwrites current guest state; require downtime and a separate recovery point when data matters.
- Before restore, resolve VMID/CTID collision, target storage, network mapping, ownership, and expected overwrite behavior.
- Before prune or delete, show the exact backup set and retention result.

## Cluster, Migration, HA, and Replication

- Require healthy quorum before cluster-wide mutation.
- Verify source and target versions, CPU compatibility, network/bridge names, storage accessibility, migration network, target capacity, and local resource mappings.
- Save the returned UPID and monitor the task on the node named by the API.
- After migration, verify owner node, guest state, storage location, HA state, agent health, and traffic path.
- Do not change HA and manually force the same workload at the same time without a single coherent plan.

## Network and Firewall

Network mutations can remove management access to the entire node or cluster.

Before applying:

- preserve the current PVE network configuration and relevant firewall/SDN state;
- identify the physical NIC, bridge, bond, VLAN, management IP, gateway, routes, and guest dependencies;
- verify bridge names exist on every migration target;
- hold an independent second session and a tested console or out-of-band recovery path;
- prepare an exact timed or console-driven rollback;
- account for cloud-provider anti-spoofing, MAC, ENI, VLAN, and routed-IP constraints rather than assuming an L2 bridge is accepted upstream.

Preview pending configuration through supported PVE interfaces. Do not blindly restart networking over the only management session. After application, verify management access, cluster traffic, storage traffic, guest ingress and egress, routing source selection, firewall state, and reboot persistence.

## Permissions and Tokens

- Read current effective ACLs and inheritance before modification.
- Use dedicated users, tokens, roles, paths, and pools; avoid broad `/` scope unless justified.
- Keep token privilege separation enabled.
- Do not display token secrets after creation or write them into files, memory, or logs.
- Test a new least-privilege identity before revoking the old recovery path.
- Permission and token mutations require an independently working administrator identity.

## Updates and Reboots

- Check the installed release, repositories, subscription state, package candidates, known release notes, cluster compatibility, and reboot requirement.
- In clusters, update one node at a time using an availability and workload-evacuation plan.
- Do not mix a major-version upgrade with unrelated network, storage, or cluster topology changes.
- A package command returning zero does not prove the node or workloads recovered. Verify API, quorum, services, storage, guests, and traffic after reboot.

## UPID Completion Gate

For every asynchronous operation:

1. save the exact UPID and node;
2. poll task status until `stopped`;
3. require `exitstatus=OK`;
4. on failure, retrieve and preserve the task log;
5. do not blindly resubmit;
6. verify resulting object state and workload behavior.

## Verification and Reporting

Report four distinct facts:

1. **Request:** the sanitized operation that was attempted.
2. **Task:** UPID, terminal status, and exit status.
3. **State:** resulting API and configuration evidence.
4. **Service:** guest, storage, cluster, and network behavior observed after the change.

If only a plan, dry-run, or offline command check was performed, label it as such and do not claim live PVE acceptance.
