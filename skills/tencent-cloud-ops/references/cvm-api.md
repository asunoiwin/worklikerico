# CVM API 3.0 operations

## Contents

- Source-of-truth and service rules
- Complete catalog routing
- Live instance information retrieval
- Instance lifecycle and destructive operations
- Configuration, billing, network, and access
- Images, keys, disks, and recovery
- Completion and rollback gates

## Source of truth and service rules

Use the current [CVM API 3.0 overview](https://cloud.tencent.com/document/api/213/15689) and then open the exact action page before constructing a request. The public endpoint is `cvm.tencentcloudapi.com`; the current CVM API version is `2017-03-12`; TCCLI uses service `cvm`.

Do not use old `cvm.api.qcloud.com` examples or API 2017 action names. Some overview links can still route to old pages; trust the exact current API 3.0 action page and its declared `Action`, endpoint, version, regions, parameters, state restrictions, batch limit, and completion method.

The tables below are a capability router, not a frozen substitute for the official action catalog. If the requested operation is absent, search the current official overview by resource and verb. Never invent an action name from console wording or a CAM-only/internal action.

## Complete catalog routing

Route any CVM request through the current overview's complete families: regions/zones; instances and billing; dedicated hosts; cloud-hosted physical servers; placement groups; images; key pairs; CVM security-group associations; CVM network attributes; launch templates; maintenance tasks; and HPC/other resources. This skill spells out common and high-risk actions below, while niche actions must be taken from their current exact action page. “Not listed below” never means “unsupported,” and “sounds plausible” never means an action exists.

## Live instance information retrieval

Never write returned inventory into this skill. Query it live, paginate completely, correlate cross-service resources, and keep only a redacted operation snapshot outside the skill when an audit record is required.

| Information | Primary read actions | Required interpretation |
|---|---|---|
| Regions and zones | `DescribeRegions`, `DescribeZones` | Region/zone availability is not interchangeable; keep region explicit in every call. |
| Instance type and purchasable configuration | `DescribeInstanceFamilyConfigs`, `DescribeInstanceTypeConfigs`, `DescribeZoneInstanceConfigInfos` | Resolve family, CPU, memory, architecture, local/cloud disk constraints, stock and supported charge mode before create or resize. |
| Instance inventory and current operation | `DescribeInstances`, `DescribeInstancesStatus`, `DescribeInstancesAttributes` | Collect ID/name, state, zone, type, CPU/memory, OS/image metadata, charge type, expiry, system/data disks, bandwidth, VPC/subnet, private/public addresses, security groups, tags, latest operation and latest-operation state. Query user data only when required and treat it as sensitive. [DescribeInstances](https://cloud.tencent.com/document/api/213/15728) is paginated and can filter by ID, name, billing mode and other documented filters. |
| Operation eligibility and quotas | `DescribeInstancesOperationLimit`, `DescribeInstancesModification`, `DescribeAccountQuota`; `InquiryPriceTerminateInstances` before a return when applicable | Treat eligibility, quota, refund/return price and restrictions as live state; do not infer them from instance state alone. |
| Bandwidth | `DescribeInstanceInternetBandwidthConfigs`, `DescribeInternetChargeTypeConfigs` | Capture charge type, cap, bandwidth package/EIP dependencies and price impact. |
| Attached storage | CVM instance fields plus current CBS `DescribeDisks`, snapshot and policy reads | CVM does not own the full disk lifecycle; query CBS before resize, detach, reinstall or terminate. |
| Network dependency graph | CVM instance fields plus VPC `DescribeNetworkInterfaces`, `DescribeAddresses`, `DescribeSubnets`, `DescribeRouteTables`, security-group reads | A public IP filter does not replace complete EIP/ENI enumeration. |
| Access and recovery | `DescribeKeyPairs`, `DescribeInstanceVncUrl`, rescue/diagnostic reads when listed | Treat VNC URLs and credentials as ephemeral secrets; never log them. |
| Images | `DescribeImages`, `DescribeImageSharePermission`, `DescribeImageQuota`, `DescribeImportImageOs`, `DescribeImageFromFamily` | Resolve ownership, OS, architecture, state, family, sharing, quota, region and compatibility before create/reinstall/import. |

## Instance lifecycle and destructive operations

| Intent | Official action family | Precondition and completion gate | Rollback boundary |
|---|---|---|---|
| Price a new instance | `InquiryPriceRunInstances` | Use the same material configuration intended for create; pricing is not a capacity reservation. | Read-only. |
| Create | `RunInstances` | Verify balance, quota/stock, image, type, disk, VPC/subnet, IP availability, security groups, key/login method, charge mode, user data and client token. The API is asynchronous; poll every returned ID with `DescribeInstancesStatus`/`DescribeInstances`: `PENDING` must reach `RUNNING`, while `LAUNCH_FAILED` is failure. Then verify dependencies and latest operation. | Terminate only newly created, unused instances after billing and disk/EIP retention review. |
| Start | `StartInstances` | Require stopped state and no conflicting latest operation; poll to `RUNNING` and latest-operation success. | Stop only if workload policy permits. |
| Stop | `StopInstances` | Drain workload first; prefer normal shutdown. Force stop is equivalent to power loss and needs explicit approval. Poll to stopped state. | Start; memory state is unrecoverable. |
| Reboot | `RebootInstances` | Only supported states; prefer normal reboot. Force reboot requires explicit data-loss acceptance. Poll back to `RUNNING` and latest-operation success. | No true inverse; use service recovery or independent image/snapshot. See [RebootInstances](https://cloud.tencent.com/document/api/213/15742). |
| Reinstall/switch OS | `InquiryPriceResetInstance` where applicable, then `ResetInstance` | Capture image/architecture compatibility, system-disk type, data-disk handling, hostname, login method, cloud-init/user data, ENI/EIP/security-group dependencies and a validated backup. System disk is formatted. Poll `DescribeInstances`. | Destructive. Recover only from a separately validated image/snapshot/backup. See [ResetInstance](https://cloud.tencent.com/document/api/213/15724). |
| Reset login password | `ResetInstancesPassword` | Never place the password in CLI arguments, logs or durable files. Running instances can require shutdown/`ForceStop`; normal stop is preferred. Poll latest operation. | No inverse; rotate again through a secure channel. See [ResetInstancesPassword](https://cloud.tencent.com/document/product/213/15736). |
| Schedule or remove lifecycle action | `DescribeInstancesActionTimer`, `ImportInstancesActionTimer`, `DeleteInstancesActionTimer` | Re-read timer, target and timezone; verify resulting timer object. | Delete/restore the saved prior timer only before it fires. |
| Return/delete instance | `InquiryPriceTerminateInstances` where applicable, then `TerminateInstances` | Exact full IDs, current state, billing, auto-renewal, system/data disk release flags, snapshots/images, EIPs, ENIs, CLB, DNS and workload retention must be explicit. A postpaid instance is destroyed directly. A prepaid instance's first call moves it to the recycle bin; a second call destroys it irreversibly. Batch targets must use one charge type. Re-read immediately before the call. | Destructive; released instance identity and local/system data are not recoverable. Recreate only from independent backups. |

Never use undocumented purge/destroy actions as a substitute for the public `TerminateInstances` workflow. A successful request ID is acceptance, not completion.

## Configuration, billing, network, and access

| Intent | Actions to locate in the current official catalog | Mandatory checks |
|---|---|---|
| Change instance type | `InquiryPriceResetInstancesType`, then `ResetInstancesType` | Query compatible modifications and operation limits; inspect local-disk, architecture, family, charge and shutdown constraints; poll latest operation. |
| Resize instance data disks | `InquiryPriceResizeInstanceDisks`, then `ResizeInstanceDisks`, or current CBS resize action for elastic disks | Identify disk ownership and filesystem expansion responsibility; capacity cannot normally be reduced. |
| Change disk medium | `ModifyInstanceDiskType` where supported | Query exact compatibility, price and interruption constraints; verify both CVM and CBS after mutation. |
| Change public bandwidth cap | `InquiryPriceResetInstancesInternetMaxBandwidth`, then `ResetInstancesInternetMaxBandwidth` | Inspect EIP/bandwidth-package ownership, charge mode and price before mutation. |
| Change instance charge type | inquiry plus `ModifyInstancesChargeType` | Price, attached portable-data-disk behavior, balance/order and unsupported instance classes. Poll latest operation. |
| Renew and auto-renew | `InquiryPriceRenewInstances`, `RenewInstances`, `ModifyInstancesRenewFlag` | Confirm duration, order price, expiry, disk/EIP renewal coupling and billing authorization. |
| Rename, tag or project | `ModifyInstancesAttribute`, `ModifyInstancesProject`, and current Tag service actions | Save exact previous values; project/tag operations can have separate CAM semantics. |
| Move VPC/subnet or change primary private IP | `ModifyInstancesVpcAttribute` | This can stop/restart instances. Verify zone, VPC/subnet/IP, address availability, ENIs, CLB and routing dependencies. Poll latest operation and rebuild the complete network graph. Use the current API 3.0 action page, not old `UpdateInstanceVpcConfig`. |
| Attach/detach security groups | `AssociateSecurityGroups`, `DisassociateSecurityGroups` | Read expanded ordered policies; preserve management access and at least one valid group. Verify CVM and ENI associations. |
| Bind/unbind key pairs | `AssociateInstancesKeyPairs`, `DisassociateInstancesKeyPairs`; manage keys with `CreateKeyPair`, `ImportKeyPair`, `ModifyKeyPairAttribute`, `DeleteKeyPairs`, `DescribeKeyPairs` | Binding can replace password login behavior depending on image/OS. Private key material is returned only at creation and must never be logged or embedded. |
| Rescue or management console | current `EnterRescueMode`, `ExitRescueMode`, `DescribeInstanceVncUrl`, diagnostic actions when public in the API catalog | Treat as privileged recovery, validate filesystem and networking afterward, and never persist the VNC URL. |

## Images, keys, disks, and recovery

- Images: `DescribeImages`, `DescribeImageQuota`, `DescribeImportImageOs`, `DescribeImageFromFamily`, `CreateImage`, `DeleteImages`, `ModifyImageAttribute`, `SyncImages`, `ModifyImageSharePermission`, `DescribeImageSharePermission`, `ImportImage`, and `ExportImages` as supported on the exact current page. Wait for image state to become usable before create/reinstall. Deleting or unsharing an image is destructive for future recovery paths.
- Operating-system conversion: `ConvertOperatingSystems` is distinct from reinstall. Run its documented dry-run/precheck, validate source/target OS, TAT availability, network, disk space and a fresh snapshot. Poll its returned `TaskId` by the exact documented mechanism, then verify OS, services and workload. Treat a successful conversion as irreversible; restoring from the validated snapshot is recovery, not an API inverse.
- Keys: use the key-pair actions above. Never store a returned private key in the skill, transcript, operation record, repository, or shell history.
- Disks and snapshots: use the current CBS API for authoritative disk, snapshot, backup, attachment, initialization, resize and deletion operations. Before reinstall or termination, distinguish system disk, local disk, elastic data disk and delete-with-instance policy.
- Recovery: an image/snapshot existing is not proof of recoverability. Verify its state, coverage, region, encryption/key access and a restore procedure before relying on it as rollback.

## Completion and rollback gates

1. Re-read `DescribeInstances` immediately before mutation and stop on target/state/dependency drift.
2. For lifecycle and configuration actions, correlate the mutation `RequestId` with `LatestOperationRequestId` when exposed, then poll until both the expected instance state and `LatestOperationState=SUCCESS` are observed; stop on `FAILED`, operation mismatch or timeout.
3. For create, verify every returned instance ID, attached disk, network address, security group, login path and billing mode.
4. For network changes, follow [vpc-network-api.md](vpc-network-api.md) and verify control plane, dependency graph and workload paths.
5. For destructive operations, validate independent backup/rebuild evidence before the request. Never describe recreation as rollback when identity, IP or data cannot be restored.
6. Record request IDs and redacted before/after summaries, not credentials or full live responses.

CAM authorization granularity is action-specific and changes over time. Confirm each action in the current [CVM CAM authorization table](https://cloud.tencent.com/document/product/598/57095); do not turn the action families above into a wildcard policy.
