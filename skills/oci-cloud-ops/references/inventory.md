# Account inventory and quota checks

Use this reference for read-only account, availability-domain, quota, usage, and instance inventory.

For a repeatable redacted report, install the official Python SDK in an isolated environment and run:

```bash
python scripts/oci_inventory.py --profile PROFILE --output /secure/path/oci-inventory.json
```

Repeat `--profile` to inspect more than one named profile. The script is read-only, omits terminated instances by default, prints only OCID suffixes, rejects group/world-readable config or key files, and writes output with mode `0600`. It does not prove Always Free eligibility or physical host capacity.

## Minimum identity and scope

Work from a named CLI profile:

```bash
oci --profile PROFILE iam tenancy get --tenancy-id TENANCY_OCID
oci --profile PROFILE iam region-subscription list --tenancy-id TENANCY_OCID --all
oci --profile PROFILE iam availability-domain list --compartment-id TENANCY_OCID --all
```

The config file normally lives at `~/.oci/config`. Check that the config and private key are not group/world readable. Prefer a session token, instance principal, or a least-privilege API key where practical. Never create a temporary config containing a private key copied from chat.

`get_tenancy` identifies the Home Region key; `list_region_subscriptions` identifies enabled regions. Do not infer Home Region from the profile's current `region` value.

## Limits, quotas, and physical capacity

Discover live names instead of hardcoding old limit identifiers:

```bash
oci --profile PROFILE limits service list --compartment-id TENANCY_OCID --all
oci --profile PROFILE limits definition list --compartment-id TENANCY_OCID --service-name compute --all
oci --profile PROFILE limits value list --service-name compute --compartment-id TENANCY_OCID --all
oci --profile PROFILE limits resource-availability get \
  --service-name compute \
  --limit-name LIMIT_NAME \
  --compartment-id COMPARTMENT_OCID \
  --availability-domain AVAILABILITY_DOMAIN
```

The actual `service-name`, `limit-name`, and required scope come from the returned definitions. Query every applicable AD or regional scope. Report `limit`, `used`, `available`, `fractionalUsed`, and `fractionalAvailable` when present. Also identify compartment quota policies when they may reduce the Oracle-set service limit.

Limits/usage do not prove host capacity. If a launch is planned, optionally use Compute Capacity Reports where supported, but a report is a point-in-time signal rather than a reservation.

Official sources to refresh:

- [Service Limits](https://docs.oracle.com/en-us/iaas/Content/General/service-limits/overview.htm)
- [Viewing Limits and Usage](https://docs.oracle.com/en-us/iaas/Content/General/service-limits/view-tenancy.htm)
- [Always Free Resources](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm)
- [Out of Host Capacity](https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/troubleshooting-out-of-host-capacity.htm)

## Resource inventory

State which compartments were inspected. For a full tenancy, enumerate active compartments recursively, then query each relevant compartment and subscribed region with pagination enabled.

At minimum collect:

- Compute instances: display name, OCID suffix, AD/fault domain, shape, OCPU, memory, lifecycle state, image, creation time, freeform/defined tags.
- Boot volumes and attachments: size, state, encryption, backup policy, whether preserved on termination.
- VNIC attachments and VNICs: subnet, private IPs, public IP objects, NSG memberships.
- Network path: subnet public/private flag, route table, internet/NAT gateway, security lists, NSGs.
- Reserved and ephemeral public IPs, including assignment state.

Useful commands:

```bash
oci --profile PROFILE compute instance list --compartment-id COMPARTMENT_OCID --all
oci --profile PROFILE compute vnic-attachment list --compartment-id COMPARTMENT_OCID --all
oci --profile PROFILE bv boot-volume list --compartment-id COMPARTMENT_OCID --availability-domain AVAILABILITY_DOMAIN --all
oci --profile PROFILE network public-ip list --compartment-id COMPARTMENT_OCID --scope REGION --all
```

Use `oci network vnic get`, subnet/route-table/security-list reads, and NSG rule reads for the selected instance. Do not claim an instance has no public IP solely because the VNIC field is empty; resolve the private IP and public IP object relationship.

## Required report format

Report these sections in plain language:

1. Account scope: profile label, tenancy suffix, Home Region, subscribed regions, compartments checked.
2. Availability and entitlement: ADs, shape-relevant limit/used/available values, quota-policy effect, and whether Always Free eligibility is confirmed by current official policy.
3. Existing machines: one row per instance with shape, resources, state, boot volume, private/public IP.
4. Network exposure: only material findings, especially `0.0.0.0/0`, all-protocol rules, and password SSH.
5. Boundary: what is a live API fact, what is current policy, and what remains a capacity/cost inference.
