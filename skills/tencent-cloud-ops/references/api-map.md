# Tencent Cloud cross-service API map

Use this file for service ownership, dependency ordering and completion gates. Load [cvm-api.md](cvm-api.md) for compute actions and [vpc-network-api.md](vpc-network-api.md) for network actions.

## Official catalogs

- [CVM API 3.0 overview](https://cloud.tencent.com/document/api/213/15689): endpoint `cvm.tencentcloudapi.com`, version `2017-03-12`, TCCLI service `cvm`.
- [VPC API 3.0 overview](https://cloud.tencent.com/document/product/215/15755): endpoint `vpc.tencentcloudapi.com`, version `2017-03-12`, TCCLI service `vpc`.
- [Private DNS API 3.0 overview](https://cloud.tencent.com/document/api/1338/55956): endpoint `privatedns.tencentcloudapi.com`, version `2020-10-28`, TCCLI service `privatedns`; most actions do not use the common `Region` parameter.
- [CBS API](https://cloud.tencent.com/document/api/362): authoritative for elastic disks, snapshots and related policies; TCCLI service `cbs`.
- [Cloud Monitor API](https://cloud.tencent.com/document/api/248): metrics and alarms; TCCLI service `monitor`.
- [CloudAudit API](https://cloud.tencent.com/document/product/629/35332): audit-event lookup; TCCLI service `cloudaudit`.
- [CAM API and authorization tables](https://cloud.tencent.com/document/product/598): identities, policies, roles and action granularity; TCCLI service `cam` or `sts` as documented.

Always open the exact current action page. Do not infer service ownership from the resource's console page: instance security-group association uses CVM actions, ENI/security policies primarily use VPC actions, disks use CBS, and metrics use Monitor.

## Common dependency order

### Read before any CVM mutation

1. CVM instance, state, latest operation, type/OS/image, charge, disks and operation limits.
2. VPC/subnet, all ENIs/private IPs, EIPs, security groups, routes, NAT/gateways and load-balancing dependencies.
3. CBS disks/snapshots/delete-with-instance policy.
4. Monitoring/health and recent CloudAudit events when relevant.

### Create path

1. Query region/zone, quota, stock, pricing and supported configuration.
2. Resolve or create VPC/subnet/routes/security resources.
3. Resolve image, key/login method and storage.
4. Create the CVM with an idempotency token where supported.
5. Poll all returned IDs; then verify storage, network, access, monitoring and billing.

### Delete path

1. Drain workload and capture an independent recoverable backup.
2. Inventory DNS/LB, EIP, ENI/private IP, routes, NAT/gateway, security, disk/snapshot and billing dependencies.
3. Remove only dependencies explicitly in scope, from consumers toward providers.
4. Terminate/release the target with exact full identifiers.
5. Verify absence, residual charges and intentionally retained resources.

Never cascade-delete merely because the API reports a dependency conflict.

## Completion gates

- **CVM lifecycle/configuration:** correlate the mutation `RequestId` with `LatestOperationRequestId` when exposed, then poll `DescribeInstances` until the expected state and `LatestOperationState=SUCCESS`; stop on failure, timeout or target drift.
- **CVM create:** a returned ID list and request ID mean accepted. Poll every ID and verify attached dependencies and billing.
- **VPC task-based actions:** follow the exact action page. When it documents a task result, poll the documented VPC task-result action and then re-read the resource. Do not convert an arbitrary request ID into a task ID.
- **EIP task actions:** when a response contains `TaskId`, poll `DescribeTaskResult` to terminal success and re-read `DescribeAddresses`/the relevant EIPv6 object.
- **CBS asynchronous actions:** poll the documented disk/snapshot state with CBS reads; verify attachment from both CBS and CVM.
- **Routes, security groups and ACLs:** re-read the complete ordered policy and associations; synchronous transport success is not traffic success.
- **Gateways and connectivity:** verify both ends, propagated/static routes, bandwidth and workload traffic.
- **CloudAudit:** use request ID for correlation, but never treat audit-event arrival as control-plane completion.

Use bounded retries with documented rate limits. Preserve the same idempotency token only when retrying the same logical request.

## Three-layer verification

1. **Control plane:** target resource reached its documented terminal state.
2. **Dependency graph:** bindings, routes, addresses, policies, disks and billing match the approved contract with no drift.
3. **Workload path:** health and intended traffic succeed from the right vantage points; explicitly forbidden traffic remains denied.

Report partial success as partial success. Roll back only with saved exact before-state and in reverse dependency order.

## Non-persistence rule

This skill contains no remembered customer inventory. Never add live account IDs, UINs, regions selected for one customer, instance IDs, resource IDs, hostnames, IPs, passwords, keys, images, hardware profiles or API responses to any file in this skill. Reusable examples must use placeholders or documentation-only values. A future task must start with fresh read APIs even when the same machine was operated previously.
