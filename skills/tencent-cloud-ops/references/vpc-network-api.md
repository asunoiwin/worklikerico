# VPC and network API 3.0 operations

## Contents

- Source-of-truth and service rules
- Live network inventory
- Core VPC, subnet, route, ENI, EIP and security operations
- Gateways and connectivity
- IPv6, observability and advanced networking
- Completion, traffic and rollback gates

## Source of truth and service rules

Use the current [VPC API 3.0 overview](https://cloud.tencent.com/document/product/215/15755) and exact action page. The public endpoint is `vpc.tencentcloudapi.com`; current VPC API version is `2017-03-12`; TCCLI uses service `vpc`. The overview contains the live families for VPC, subnet, routes, EIP/EIPv6, HAVIP, ENI, bandwidth, NAT, VPN, direct-connect gateway, CCN, security groups, network ACLs, network parameters, detection, flow logs, DHCP IP, PrivateLink, peering and traffic mirroring.

Private DNS is a separate service: use the [Private DNS API 3.0 overview](https://cloud.tencent.com/document/api/1338/55956), endpoint `privatedns.tencentcloudapi.com`, version `2020-10-28`, and TCCLI service `privatedns`. Most Private DNS actions do not use the common `Region` parameter; follow each action page instead of copying VPC invocation patterns.

Do not use the retired VPC API 2017/2.0 action names when an API 3.0 action exists. Open the exact current action page before mutation and confirm action, endpoint, version, regions, parameter schema, task/completion behavior, price impact and CAM granularity.

The action families below route discovery; they do not freeze Tencent Cloud's evolving catalog. Search the current overview for any omitted feature instead of inventing an action name.

## Live network inventory

Never persist returned topology in this skill. Reacquire it for every task and paginate completely.

Build the smallest complete dependency graph:

1. Account/region limits and attributes: `DescribeAccountAttributes`, `DescribeVpcLimits`, address/ENI/security-group/NAT/VPN/CCN quotas as exposed by current actions.
2. VPC and subnets: `DescribeVpcs`, `DescribeVpcResourceDashboard`, `DescribeSubnets`, `DescribeSubnetResourceDashboard`, `DescribeUsedIpAddress` and IPv6/assistant-CIDR state.
3. Routing: `DescribeRouteTables`, subnet associations, enabled/disabled routes, high-priority routes and all next-hop resources.
4. Compute interfaces: `DescribeNetworkInterfaces`, `DescribeNetworkInterfaceLimit`, primary/auxiliary ENI attachment, primary/secondary private IPs, IPv6 addresses and security-group associations.
5. Public addressing: `DescribeAddresses`, `DescribeAddressQuota`, EIPv6, charge/bandwidth mode, binding target, task state, arrears/block and direct-connection flag.
6. Security: `DescribeSecurityGroups`, policies, expanded policies and associations; `DescribeNetworkAcls` plus subnet associations and ordered stateless rules.
7. Egress and connectivity: NAT/public/private NAT, VPN/customer gateways/connections, direct-connect gateways, peering, CCN instances/attachments/routes/bandwidth, PrivateLink endpoints/services.
8. Name resolution and operations evidence: Private DNS zones/records/VPC associations/endpoints/forwarding, network detection, flow logs, traffic mirroring, monitoring and CloudAudit request correlation.

## Core resources

### VPC and subnet

| Resource | Read actions | Mutation families | Hard checks |
|---|---|---|---|
| VPC | `DescribeVpcs`, `DescribeVpcLimits`, `DescribeVpcResourceDashboard`, `DescribeAccountAttributes` | `CreateVpc`, `CreateDefaultVpc`, `ModifyVpcAttribute`, `DeleteVpc`; assistant CIDR and IPv6 assignment/unassignment actions | CIDR overlap, DNS/DHCP/IPv6 intent, quotas, dependent subnets/routes/gateways/ENIs. Default VPC and default route-table semantics differ from custom resources. |
| Subnet | `DescribeSubnets`, `DescribeSubnetResourceDashboard`, `DescribeUsedIpAddress` | `CreateSubnet`, `CreateSubnets`, `ModifySubnetAttribute`, `DeleteSubnet`, `AssignIpv6SubnetCidrBlock`, `UnassignIpv6SubnetCidrBlock` | VPC containment, overlap, zone, available IPs, route table, ACL, ENIs and managed-service dependencies. |

Deleting a VPC, subnet or auxiliary/IPv6 CIDR is destructive and normally dependency-blocked. Never cascade-delete blockers unless each dependent resource is explicitly approved.

### Route tables

Read `DescribeRouteTables` and the complete association/route objects. Current mutation families include `CreateRouteTable`, `ModifyRouteTableAttribute`, `DeleteRouteTable`, `CreateRoutes`, `DeleteRoutes`, `ReplaceRoutes`, `EnableRoutes`, `DisableRoutes`, `ReplaceRouteTableAssociation`, and the current high-priority-route actions.

Before mutation:

- save the exact table, subnet association, route order/state and next-hop object;
- detect equal/overlapping destinations, longest-prefix effects, ECMP/main-backup behavior and local/container CIDRs;
- validate next-hop type, ID, health, VPC, region and route propagation;
- preserve an out-of-band management path that does not depend on the route being changed.

Route tables select by destination and priority, not by a guest's source IP. Do not present a subnet route-table change as a solution for per-source-address policy routing. Current route next hops can include NAT, peering, VPN, direct-connect gateway, CVM, HAVIP, CCN and other documented gateway types. See the [current route-table model](https://cloud.tencent.com/document/product/215/39406).

### ENIs and private addresses

| Intent | Read | Mutation | Gate |
|---|---|---|---|
| Create/delete ENI | `DescribeNetworkInterfaces`, `DescribeNetworkInterfaceLimit`, subnet/IP/SG inventory | `CreateNetworkInterface`, `CreateAndAttachNetworkInterface`, `ModifyNetworkInterfaceAttribute`, `DeleteNetworkInterface` | Same region/VPC/subnet/zone requirements; only delete a safe, unattached ENI without dependent addresses. |
| Attach/detach | instance plus ENI and task inventory | `AttachNetworkInterface`, `DetachNetworkInterface` | Verify compatible instance/zone/VPC, security groups, EIPs and guest-OS network plan. Complete documented VPC task polling before re-read. |
| Private IPv4 | ENI/subnet/used-IP inventory | `AssignPrivateIpAddresses`, `UnassignPrivateIpAddresses`, `ModifyPrivateIpAddressesAttribute`, `MigratePrivateIpAddress` | Do not assume the guest OS auto-configures an assigned address. Verify duplicate use, prefix, return path and reboot persistence. `UnassignPrivateIpAddresses` automatically disassociates a bound EIP; treat that as part of the approved change. |
| IPv6 | current ENI IPv6 describe/assign/unassign actions | exact current API actions | Validate VPC/subnet IPv6 CIDRs, route/security posture and guest support. |
| ENI security groups | ENI type plus expanded policies | `AssociateNetworkInterfaceSecurityGroups`, `DisassociateNetworkInterfaceSecurityGroups` | These actions are for supported auxiliary ENIs; manage primary-ENI exposure through CVM association semantics. Never leave an unintended unrestricted ENI. |

For documented asynchronous ENI operations—including create-and-attach, attach/detach/delete, private-IP assign/unassign or migration, and IPv6 assign/unassign—take the returned `RequestId` as the VPC task ID only when the exact action page says so, then poll [`DescribeVpcTaskResult`](https://cloud.tencent.com/document/api/215/59037) until `SUCCESS` or `FAILED`. Re-read both ENI and CVM afterward and verify guest networking. Do not claim that detaching an ENI automatically unbinds its EIP unless that action's current page explicitly says so.

### EIP and EIPv6

Use `DescribeAddresses`/`DescribeAddressQuota` and the current EIPv6 read families before every operation.

- Allocate: `AllocateAddresses` or the current EIPv6 allocation action. Confirm quota, charge mode, bandwidth and price first.
- Bind/unbind: `AssociateAddress`, `DisassociateAddress`, with exact CVM/ENI/private-IP target semantics from the current action page.
- Modify: `ModifyAddressAttribute`, bandwidth/charge actions and bandwidth-package association actions currently listed.
- Convert: `TransformAddress` only for documented ordinary-public-IP conversion scenarios.
- Release: `ReleaseAddresses` or current EIPv6 release action only after dependency and billing review.

An unbound EIP can still incur charges. If a mutation returns `TaskId`, poll `DescribeTaskResult` to terminal success and re-read `DescribeAddresses`. For direct connection, read the official [EIP direct-connection guide](https://cloud.tencent.com/document/product/1199/41709) and require independent console/VNC recovery plus guest routing verification.

### Security groups and network ACLs

Security groups are stateful instance/ENI controls. Read `DescribeSecurityGroups`, `DescribeSecurityGroupPolicies`, `DescribeSecurityGroupExpandedPolicies`, association statistics and attached resources. Current families include create/modify/delete group, create/replace/delete policies, CVM `AssociateSecurityGroups`/`DisassociateSecurityGroups`, and supported ENI association actions.

Network ACLs are stateless subnet controls. Use `DescribeNetworkAcls`, `CreateNetworkAcl`, `ModifyNetworkAclAttribute`, current entry-replacement actions, subnet association/disassociation actions and `DeleteNetworkAcl` as named in the current overview. A new ACL defaults to deny in both directions, return traffic needs an explicit matching rule, and each subnet can associate with only one ACL; verify these current constraints before association.

For both layers, save the complete ordered inbound/outbound policy and associations. Preserve management and return traffic. Verify intended allows and intended denies; a successful API response is not a traffic test.

## Gateways and connectivity

### Public and private NAT

Use current NAT inventory actions such as `DescribeNatGateways`, address/rule reads, and private-NAT reads. Mutation families include:

- `CreateNatGateway`, `ModifyNatGatewayAttribute`, `DeleteNatGateway`;
- NAT EIP/address association and disassociation actions in the current catalog;
- `CreateNatGatewaySourceIpTranslationNatRule`, `DeleteNatGatewaySourceIpTranslationNatRule`;
- `CreateNatGatewayDestinationIpPortTranslationNatRule`, corresponding modify/delete actions;
- current `CreatePrivateNatGateway`, translation-rule, modify and delete families.

Verify EIP ownership, SNAT/DNAT overlap, ports/protocols, route-table next hops, flow symmetry, connection impact and charges. After [`CreateNatGateway`](https://cloud.tencent.com/document/api/215/36721), poll `DescribeNatGateways` until `State=AVAILABLE` before adding dependent routes or rules. [`DeleteNatGateway`](https://cloud.tencent.com/document/api/215/36719) automatically deletes routes that point to that NAT gateway and disassociates its EIPs; record those approved cascade effects, then verify the route tables and retained EIPs explicitly.

### VPC peering

Use the current `DescribeVpcPeeringConnections` and create/accept/reject/modify/delete/enable action family. Check both accounts/regions/VPC CIDRs, route tables on both sides, DNS needs and overlapping networks. Completion requires connection state `ACTIVE`, the required routes on both VPC sides, and bilateral traffic verification. Peering is non-transitive; deleting either side interrupts the link. Cross-region capabilities and billing can differ; trust the exact current page.

### Cloud Connect Network

Use current CCN actions including `DescribeCcns`, `CreateCcn`, `ModifyCcnAttribute`, `DeleteCcn`, `AttachCcnInstances`, `DetachCcnInstances`, attachment/route-table/route reads, route enable/disable/accept/publish actions and region-bandwidth actions.

Before attachment or route propagation changes, inventory all attached VPC/VPN/direct-connect resources, CIDRs, route conflicts, propagation/selection policies and inter-region/cross-border bandwidth. Completion requires the intended attachment state to be `ACTIVE`, expected routes without unresolved conflicts, bandwidth configuration, and bilateral traffic verification. Cross-border connectivity also requires the documented compliance prerequisites. Ensure rollback does not strand other attachments.

### VPN and direct-connect gateway

- VPN: current `Describe*` families for VPN gateways, customer gateways, VPN connections and SSL VPN; create/modify/delete each resource in dependency order. Protect pre-shared keys and client credentials as secrets.
- Direct-connect gateway: current describe/create/modify/delete and route/association actions. Direct Connect service resources can belong to a different API service; query both sides before mutation.

Hybrid connectivity changes can affect remote networks outside the Tencent account. Require explicit route ownership, maintenance window and a remote-side operator/verification path.

### PrivateLink

Use the current PrivateLink endpoint service, endpoint and endpoint-connection action families from the VPC API overview. Inventory service permissions, target load balancers/resources, DNS, security groups and connection acceptance before mutation. Verify consumer and provider sides separately.

### DHCP IP

Use `DescribeDhcpIps`, `CreateDhcpIp`, `ModifyDhcpIpAttribute`, `AssociateDhcpIpWithAddressIp`, `DisassociateDhcpIpWithAddressIp`, and `DeleteDhcpIp` from the current DHCP IP catalog. Follow documented VPC task completion through `DescribeVpcTaskResult`. Deletion recycles the DHCP IP address, so treat it as destructive and re-check all address associations first.

### Private DNS

Use the separate Private DNS service to inventory and operate private zones, records, VPC associations, endpoints, forwarding rules, account sharing and operation logs. Re-read the exact action page because its endpoint, version and regional behavior differ from VPC.

- Read zones, records, VPC associations, endpoints and forwarding rules before mutation.
- For specified VPC association/disassociation actions that return `UniqId`, poll [`QueryAsyncBindVpcStatus`](https://cloud.tencent.com/document/api/1338/102361) to a terminal result and re-read the zone association.
- For batch creation actions, use the paired batch-result action named by the exact API page.
- Verify name resolution from each intended VPC and confirm that removed associations no longer resolve; an API success alone is not a DNS-path test.

## IPv6, observability, and advanced networking

- IPv6: VPC/subnet IPv6 CIDR assignment, ENI IPv6, EIPv6 and IPv6 translation are separate resource families. Do not mirror IPv4 assumptions; verify routes, ACL/SG policies, DNS and billing independently.
- HAVIP: `DescribeHaVips`, `CreateHaVip`, `ModifyHaVipAttribute`, `DeleteHaVip`, instance/ENI and EIP association actions. Coordinate guest HA software and ARP/route behavior.
- Network detection: `CreateNetDetect`, `ModifyNetDetect`, `DeleteNetDetect`, `DescribeNetDetects`, `DescribeNetDetectStates`, `CheckNetDetectState`.
- Flow logs: `CreateFlowLog`, `DescribeFlowLog`/`DescribeFlowLogs`, `ModifyFlowLogAttribute`, `EnableFlowLogs`, `DisableFlowLogs`, `DeleteFlowLog`. Confirm log destination, retention, cost and sensitive traffic metadata.
- Traffic mirroring and gateway traffic monitoring: use the current overview families; confirm capture target, scope, privacy and cost.
- Network parameter templates, bandwidth packages and snapshot policies: use their current action families and dependency reads; do not infer them from similarly named CVM APIs.

## Completion, traffic, and rollback gates

1. Re-read exact targets and all dependencies immediately before mutation.
2. If an action returns `TaskId`, poll the documented task action to terminal success. For documented VPC request-task flows, poll `DescribeVpcTaskResult`; never assume every request ID is a task ID unless the exact action page defines it that way.
3. After every mutation, re-read the resource and associations. For routes/security rules, compare the entire ordered set.
4. Verify control plane, dependency graph and workload traffic from appropriate source and destination vantage points. Test both expected access and expected denial.
5. Roll back in reverse dependency order using saved exact objects. Do not improvise an inverse for released addresses, deleted networks, terminated gateways or irreversible billing/data changes.
6. Recheck charges for EIP, NAT, VPN, CCN bandwidth, flow logs and other billable resources.

Confirm least-privilege granularity in the current [VPC CAM authorization table](https://cloud.tencent.com/document/product/598/57179). Do not use `vpc:*`; some read or create actions are operation-level and require `*`, while others support resource-level constraints.
