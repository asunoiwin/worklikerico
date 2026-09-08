---
name: tencent-cloud-ops
description: Safely discover, plan, execute, verify, and roll back Tencent Cloud compute and network infrastructure operations from the current official API documentation. Use for CVM inventory and lifecycle operations; images, keys, disks, billing and recovery; VPCs, subnets, routes, ENIs, private IPs, EIPs, NAT, security groups, ACLs, VPN, peering, CCN, IPv6, PrivateLink, Private DNS, DHCP IP, flow logs and network diagnostics; CAM least privilege; CloudAudit; or incident-safe recovery.
---

# Tencent Cloud operations

Operate from current evidence. Default to read-only discovery; mutate only when the user has asked for the exact cloud change.

Treat the current Tencent Cloud API 3.0 overview and the exact action page as the source of truth. Do not derive the skill's capabilities, action names, parameters, or supported regions from a previous customer task, console memory, an old API version, or one machine's observed state. Re-open the current official action page before every mutation because action availability and restrictions change.

## Non-negotiable safety rules

- When the user supplies credentials and authorizes an exact read-only action, proceed directly. Consume them once through stdin/PTY or the current process environment; do not ask the user to repeat them or create a separate GUI, pipe, agent, or credential-setup workflow when direct transport works.
- Do not save or echo credentials. Keep them out of this skill, memory, source files, persistent configuration, shell history, and reports; clear runtime values after the call. If a credential was exposed in conversation, mention rotation once after reporting the result, not as a prerequisite or a repeated warning.
- Never persist an instance inventory or a previous operation's account, region, zone, instance ID, IP, image, VPC, subnet, route, ENI, EIP, security group, billing state, hostname, operating system, or hardware profile in this skill. Store only reusable query procedures and API semantics. Always reacquire live machine and dependency information from read APIs.
- Prefer STS or a workload role, but do not block a bounded read-only query merely because the user supplied an authorized permanent sub-user key. Never use a known root-account permanent key for mutations.
- Do not run `tccli configure`, persist a profile, pass authentication fields as command arguments, or enable debug output around credentials.
- Treat region, account, resource type, and exact target as separate assertions. Never infer a target from a partial name or a single IP address.
- Complete pagination for inventory APIs before declaring a resource absent.
- Record only sanitized change evidence: timestamp, operator label, action, region, masked target, pre/post state hashes or summaries, API request ID, result, and rollback result.
- Do not operate a real account merely to test this skill. Use API skeleton generation, local validation, or user-provided redacted responses instead.

Load references progressively:

- Read [references/cvm-api.md](references/cvm-api.md) for CVM information retrieval, lifecycle, reinstall, password, configuration, billing, image, key, disk, rescue, or termination work.
- Read [references/vpc-network-api.md](references/vpc-network-api.md) for any VPC or network resource, including Private DNS, cross-VPC and hybrid connectivity.
- Read [references/api-map.md](references/api-map.md) when a change crosses products or needs completion-gate and dependency ordering.
- Read [references/auth-and-audit.md](references/auth-and-audit.md) whenever credentials, permissions, TCCLI/SDK setup, CAM policy, or audit evidence are involved.

## Fast path for simple read-only checks

Use this path for a specific `Describe`, `List`, or `LookUp` request with no cloud mutation:

1. Use the target, region, and credentials already supplied in the active request. Do not search old logs for credentials or front-load a full dependency inventory.
2. Make the narrowest API call immediately. Prefer direct SDK or TC3 signing already available locally; do not install tooling when the standard library is sufficient.
3. If authentication succeeds but the target is absent, expand pagination or regions only as needed. Do not run GUI automation, spawn agents, or build a credential broker unless direct execution is genuinely unavailable.
4. Report the decisive fields, mismatches, and request ID. Stop when the user's question is answered; do not expand into ENI, EIP, route, security-group, host, or audit discovery unless the request needs it.
5. Keep credential hygiene to one short closing sentence: not saved, runtime values cleared, rotate if exposed.

The full workflow below applies to mutations, ambiguous target selection, multi-resource inventory, incident response, and dependency-sensitive diagnosis.

## Workflow

### 1. Define the outcome and stop conditions

State:

- intended end state and observable success criteria;
- account context, region, and exact target-selection rule;
- allowed downtime and whether out-of-band access exists;
- rollback trigger, rollback deadline, and the last safe point;
- whether the task is inventory-only, reversible change, disruptive change, destructive change, or cost-creating change.

If account, region, target, or desired end state remains ambiguous after read-only discovery, stop before mutation.

### 2. Establish least privilege

Derive the CAM action allowlist from the read and write actions in [references/api-map.md](references/api-map.md). Grant only required actions, target resources where the API supports resource-level authorization, required regions, and the shortest usable session duration. Do not grant service-wide wildcards for convenience.

Use TCCLI with temporary environment variables:

```zsh
(
  set +x
  trap 'unset TENCENTCLOUD_SECRET_ID TENCENTCLOUD_SECRET_KEY TENCENTCLOUD_TOKEN' EXIT
  trap 'exit 129' HUP
  trap 'exit 130' INT
  trap 'exit 143' TERM
  read -r -s "TENCENTCLOUD_SECRET_ID?Temporary secret ID: " || exit 1
  read -r -s "TENCENTCLOUD_SECRET_KEY?Temporary secret key: " || exit 1
  read -r -s "TENCENTCLOUD_TOKEN?Session token (optional for an authorized sub-user key): " || exit 1
  [[ -n "$TENCENTCLOUD_SECRET_ID" && -n "$TENCENTCLOUD_SECRET_KEY" ]] || exit 1
  export TENCENTCLOUD_SECRET_ID TENCENTCLOUD_SECRET_KEY
  [[ -n "$TENCENTCLOUD_TOKEN" ]] && export TENCENTCLOUD_TOKEN

  tccli cvm DescribeInstances --region "<REGION>" --limit 100
)
```

The subshell prevents credentials from entering the parent shell. Signal traps terminate the subshell; the exit trap then cleans up. Empty or interrupted ID/key reads fail closed before any API call. The token remains mandatory for STS credentials and optional only for an explicitly authorized permanent sub-user key. Keep values out of the command text and keep region explicit even when an environment default exists.

Use the Python SDK with already-injected credentials; include a token only for STS:

```python
import os
from tencentcloud.common import credential

args = [
    os.environ["TENCENTCLOUD_SECRET_ID"],
    os.environ["TENCENTCLOUD_SECRET_KEY"],
]
if os.environ.get("TENCENTCLOUD_TOKEN"):
    args.append(os.environ["TENCENTCLOUD_TOKEN"])
cred = credential.Credential(*args)
```

Do not serialize `cred`, log request headers, or print caught exceptions containing request material.

### 3. Build a read-only dependency snapshot

Inventory the smallest complete graph needed for the change:

1. CVM identity, state, availability zone, instance type and hardware, operating-system/image metadata, charge mode, disks, bandwidth, VPC/subnet, all ENIs, private/public addresses, security groups, keys, latest operation, and operation limits.
2. VPC CIDRs, subnet CIDRs and zones, route-table associations and routes, ENI attachments and address assignments.
3. Security-group rule directions, order/version, expanded exposure, and all attached resources.
4. EIP state, charge/bandwidth mode, target binding, arrears/block status, and direct-connection flag.
5. CloudAudit events around recent related changes.

Capture a redacted before-state summary. Re-read the decisive resource immediately before mutation to detect drift.

### 4. Produce the change contract

Show the user a compact contract containing:

- exact action and region;
- exact targets, with names and full identifiers shown only in the live confirmation message;
- expected traffic, availability, security, and billing effects;
- preconditions already verified;
- ordered API calls and idempotency token usage where supported;
- verification queries, rollback calls, and the point after which rollback is impossible.

Never combine discovery and mutation into an opaque one-liner.

### 5. Apply the confirmation boundary

No additional confirmation is required for read-only `Describe`, `List`, `LookUp`, or local skeleton-generation work.

Require explicit confirmation immediately before any of these:

- stop or reboot an instance when workload impact is not already acknowledged;
- detach or migrate an ENI/private address, disassociate an EIP, replace a route-table association, or change routes affecting reachability;
- add broad security-group exposure, replace/delete rules, or detach the last effective security group;
- enable/disable EIP direct connection or run its in-guest networking script;
- create chargeable resources, increase bandwidth, change billing mode, or renew resources;
- reset an instance, reset a login secret, release an address, delete networking resources, or terminate an instance;
- broaden CAM access, alter an audit trail, or touch production data.

The confirmation must name the action, region, target count, downtime/data/billing risk, and rollback limitation. A vague “continue” obtained before discovery is not valid confirmation.

### 6. Execute one bounded step at a time

- Re-check target state and preconditions.
- Prefer one target per request for disruptive/destructive work.
- Supply a unique client token when the API supports idempotency; reuse it only for a retry of the same logical request.
- Capture request IDs without recording authentication or full sensitive payloads.
- Apply the service-specific completion gate in [references/api-map.md](references/api-map.md). Poll with bounded backoff; a request ID, task ID, or accepted request is not success.
- Stop on target drift, unexpected dependency changes, partial batch success, authorization expansion, or a rollback trigger.

### 7. Verify from three layers

1. **Control plane:** expected resource state and latest-operation status.
2. **Dependency graph:** bindings, routes, security groups, addresses, and charge mode still match the contract.
3. **Workload path:** user-approved health check from an appropriate vantage point; for networking changes, verify both intended reachability and intended denial.

Correlate the request ID with CloudAudit when available. Report partial success as partial success.

### 8. Roll back or close

Rollback in reverse dependency order using the saved before-state, then repeat all three verification layers. Do not improvise an inverse for irreversible actions. If rollback cannot restore the prior state, stop further changes and report the exact residual state and recovery options.

Close with: outcome, sanitized targets, before/after state, request IDs, verification, audit evidence, rollback status, and residual risks.
