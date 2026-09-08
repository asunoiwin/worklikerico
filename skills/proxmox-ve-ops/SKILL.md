---
name: proxmox-ve-ops
description: Safely discover, diagnose, plan, execute, verify, and roll back Proxmox VE host, cluster, QEMU VM, LXC, storage, backup, network, firewall, HA, replication, permission, update, and task operations through the official REST API or local CLI. Use for PVE or Proxmox nodes, clusters, guests, vmbr bridges, snapshots, backups, migrations, API tokens, upgrades, or host health.
---

# Proxmox VE Operations

Operate Proxmox VE from current evidence and official interfaces. Default to read-only discovery; make every mutation bounded, reversible where possible, and independently verified.

## Load the Relevant Reference

- Read [references/api-and-auth.md](references/api-and-auth.md) before connecting, authenticating, choosing REST versus local CLI, or using `scripts/pve_api.py`.
- Read [references/operations-and-safety.md](references/operations-and-safety.md) before any mutation or when working with cluster, guest, storage, backup, network, firewall, HA, permissions, or updates.
- Consult the API Viewer matching the installed PVE version before relying on endpoint paths, parameters, or response fields. The live API schema is authoritative.

## Non-Negotiable Safety Rules

1. Default to read-only. Diagnosis or explanation does not authorize a change.
2. Resolve the exact cluster, node, VMID or CTID, storage, bridge, and object before acting. Never infer a destructive target from a partial name.
3. Never store a Proxmox hostname, inventory, API token ID, token secret, password, ticket, or CSRF token in the skill, project files, memory, shell history, logs, or command output. Enter passwords only through the wrapper's no-echo terminal prompt.
4. `root@pam` or a root-owned API token is valid when that is the environment's operating model. Before every write operation, display that privileged identity is being used, the exact targets, and the expected impact. Use a scoped token when the task or organization requires separation of duties.
5. Require verified TLS using a trusted certificate or the Proxmox cluster CA. Never use `curl -k`, `verify=False`, or an insecure TLS fallback.
6. Treat `/etc/pve` as the quorum-backed `pmxcfs` cluster filesystem. Do not edit its token, user, cluster, or guest configuration files directly when an API or supported CLI operation exists.
7. Do not expose secrets in process arguments. `scripts/pve_api.py` reads API tokens from environment variables, reads passwords only with `getpass`, and rejects secret-like request parameters on its command line.
8. Obtain explicit approval immediately before write operations. The approval prompt must name the privileged identity class, targets, action, expected impact, and rollback. Destructive operations need a separate, unmistakable warning.
9. For asynchronous operations, save the UPID, wait until the task is stopped, and accept success only when `exitstatus` is `OK`.
10. A successful API response is not completion. Verify the control plane, dependent configuration, and workload traffic path.

## Workflow

### 1. Define the Outcome and Boundaries

State:

- requested outcome;
- cluster, node, and guest or object identifiers;
- whether downtime is allowed;
- data-loss and availability risks;
- required backup, snapshot, console, or out-of-band access;
- rollback trigger and rollback action.

If two interpretations materially change the target or risk, stop and resolve the ambiguity.

### 2. Establish a Safe Connection

Use the REST API for remote management. Use local `pvesh`, `qm`, `pct`, `pvesm`, or related supported CLIs only when access to that specific host is explicitly in scope.

Read connection values from the current process environment. Verify the PVE version first and use its current API Viewer.

### 3. Build a Read-Only Inventory

Start with `scripts/pve_api.py inventory` when its sanitized summary fits the request. Otherwise query the minimum relevant set:

- `/version`;
- `/cluster/status` and `/cluster/resources`;
- `/nodes` and the target node status;
- target QEMU VM or LXC status and configuration;
- relevant storage, network, firewall, HA, replication, backup, and task state.

In a cluster, check quorum and identify the current owner node before changing a guest or cluster-wide object.

### 4. Produce a Change Contract

Before mutation, show:

- exact API method and path or supported CLI command;
- sanitized parameters;
- required privileges;
- affected targets and dependencies;
- downtime or restart behavior;
- preflight evidence;
- rollback procedure;
- post-change checks.

Use the wrapper's dry-run output where possible.

### 5. Confirm Write and High-Risk Boundaries

For any API or CLI write, show a concise permission prompt containing identity class, exact target, operation, impact, and rollback. Require explicit target-specific approval, with an additional destructive warning, for:

- stopping, shutting down, resetting, rebooting, or deleting a guest or node;
- creating, resizing, moving, detaching, wiping, or deleting disks or storage;
- snapshot rollback or deletion, backup restore, or backup pruning;
- migration, HA, replication, quorum, corosync, or cluster membership changes;
- bridge, bond, VLAN, SDN, routing, firewall, DNS, or management-address changes;
- repository, package, kernel, bootloader, upgrade, or reboot operations;
- user, realm, ACL, role, token, two-factor, or certificate changes.

Read-only operations such as inventory, status, configuration retrieval, task logs, and API schema inspection do not require approval.

### 6. Execute One Bounded Step

Do not combine unrelated mutations. Re-read the target immediately before acting, run the single approved operation, record its request result and UPID, and avoid retries until the first task has a terminal state.

For REST calls, use `scripts/pve_api.py` where its interface fits. For local CLI, inspect the installed command help or `pvesh usage` before constructing version-sensitive parameters.

### 7. Wait for Task Completion

When the API returns a UPID:

```bash
python3 scripts/pve_api.py wait-task NODE 'UPID:...'
```

Do not report success while the task is running. On failure, read the task log, preserve the original error, and decide between rollback and a new plan before retrying.

### 8. Verify in Three Layers

1. **Control plane:** API status, task exit status, current config, cluster quorum, and node health.
2. **Dependency graph:** storage activation, bridge or VLAN presence, firewall and HA state, backup or replication schedule, and owner node.
3. **Workload path:** guest boot, agent or console health, disk availability, expected ingress and egress, DNS, application health, and reboot persistence when relevant.

### 9. Close or Roll Back

Report the requested outcome, what changed, UPID and terminal result, verification evidence, remaining risk, and rollback state. If verification fails, do not conceal partial success; execute the approved rollback or stop with exact recovery steps.

## Wrapper Quick Start

Use one verified TLS mode: system trust, `PVE_CA_FILE`, or an out-of-band verified `PVE_TLS_SHA256` pin. See the authentication reference before first connection.

Password-ticket mode defaults to `root@pam` and prompts without echo:

```bash
export PVE_API_URL=https://pve.example:8006
export PVE_TLS_SHA256='AA:BB:...:FF'
python3 scripts/pve_api.py inventory
```

Set `PVE_USERNAME` only when the password identity is not `root@pam`. Never set a password environment variable.

API-token mode remains available:

```bash
export PVE_API_TOKEN_ID='operator@pve!codex'
export PVE_API_TOKEN_SECRET='current-session-secret'
python3 scripts/pve_api.py get /version
python3 scripts/pve_api.py get /cluster/resources --param type=vm
python3 scripts/pve_api.py request POST /nodes/pve/qemu/101/status/start --dry-run
PVE_ALLOW_MUTATION=1 python3 scripts/pve_api.py request POST /nodes/pve/qemu/101/status/start \
  --confirm 'node=pve,vmid=101,action=start'
```

`--dry-run` never contacts Proxmox. A real mutation requires both `PVE_ALLOW_MUTATION=1` and a nonempty `--confirm` contract.

Use `observe-cert` only to display the currently presented fingerprint. Compare it with a trusted PVE console or certificate record before setting `PVE_TLS_SHA256`; observation alone does not establish trust.

## Completion Standard

The task is complete only when the exact requested state is reached, any UPID is terminal with `exitstatus=OK`, relevant dependencies and workload behavior pass verification, and rollback status plus residual risks are reported. Offline validation of a command or plan is not production acceptance.
