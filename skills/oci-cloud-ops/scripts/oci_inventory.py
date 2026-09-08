#!/usr/bin/env python3
"""Produce a read-only, OCID-redacted OCI account inventory."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat
import sys
from typing import Any


LIMIT_PREFIXES = ("standard-a1-",)
LIMIT_NAMES = {
    "standard-e2-micro-core-count",
    "vm-standard-e2-1-micro-count",
}


def suffix(value: str | None, width: int = 12) -> str | None:
    return value[-width:] if value else None


def relevant_compute_limit(name: str | None) -> bool:
    if not name:
        return False
    if name in LIMIT_NAMES:
        return True
    return name.startswith(LIMIT_PREFIXES) and not any(
        token in name for token in ("reservable", "reserved", "dvh-")
    )


def file_mode(path: Path) -> str:
    return oct(stat.S_IMODE(path.stat().st_mode))


def check_private_file(path: Path, label: str) -> None:
    if not path.is_file():
        raise ValueError(f"{label} does not exist: {path}")
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        raise ValueError(f"{label} must not be group/world accessible: {path} ({oct(mode)})")


def iso(value: Any) -> str | None:
    return value.isoformat() if value else None


def instance_shape(instance: Any) -> dict[str, Any]:
    config = getattr(instance, "shape_config", None)
    return {
        "name": instance.shape,
        "ocpus": getattr(config, "ocpus", None),
        "memory_gb": getattr(config, "memory_in_gbs", None),
    }


def api_error(exc: Exception) -> dict[str, Any]:
    return {
        "status": getattr(exc, "status", None),
        "code": getattr(exc, "code", type(exc).__name__),
        "message": str(getattr(exc, "message", exc))[:300],
        "request_id": getattr(exc, "request_id", None),
    }


def paginate(oci: Any, call: Any, *args: Any, **kwargs: Any) -> list[Any]:
    return oci.pagination.list_call_get_all_results(call, *args, **kwargs).data


def collect_instance(oci: Any, compute: Any, network: Any, block: Any, instance: Any) -> dict[str, Any]:
    item: dict[str, Any] = {
        "name": instance.display_name,
        "ocid_suffix": suffix(instance.id),
        "state": instance.lifecycle_state,
        "availability_domain": instance.availability_domain,
        "fault_domain": instance.fault_domain,
        "shape": instance_shape(instance),
        "image_ocid_suffix": suffix(instance.image_id),
        "created_at": iso(instance.time_created),
        "vnics": [],
        "boot_volumes": [],
    }
    attachments = paginate(
        oci,
        compute.list_vnic_attachments,
        instance.compartment_id,
        instance_id=instance.id,
    )
    for attachment in attachments:
        if not attachment.vnic_id:
            continue
        vnic = network.get_vnic(attachment.vnic_id).data
        item["vnics"].append(
            {
                "name": vnic.display_name,
                "ocid_suffix": suffix(vnic.id),
                "subnet_ocid_suffix": suffix(vnic.subnet_id),
                "private_ip": vnic.private_ip,
                "public_ip": vnic.public_ip,
                "nsg_ocid_suffixes": [suffix(x) for x in (vnic.nsg_ids or [])],
                "primary": attachment.is_primary,
            }
        )
    attachments = paginate(
        oci,
        compute.list_boot_volume_attachments,
        instance.availability_domain,
        instance.compartment_id,
        instance_id=instance.id,
    )
    for attachment in attachments:
        volume = block.get_boot_volume(attachment.boot_volume_id).data
        item["boot_volumes"].append(
            {
                "name": volume.display_name,
                "ocid_suffix": suffix(volume.id),
                "state": volume.lifecycle_state,
                "size_gb": volume.size_in_gbs,
                "kms_key_ocid_suffix": suffix(volume.kms_key_id),
                "preserve_on_instance_deletion": getattr(
                    attachment, "is_preserve_boot_volume_enabled", None
                ),
            }
        )
    return item


def collect_profile(oci: Any, config_file: Path, profile: str, include_terminated: bool) -> dict[str, Any]:
    config = oci.config.from_file(str(config_file), profile)
    oci.config.validate_config(config)
    key_path = Path(os.path.expanduser(config["key_file"])).resolve()
    check_private_file(config_file, "OCI config")
    check_private_file(key_path, "OCI API private key")

    identity = oci.identity.IdentityClient(config)
    tenancy = identity.get_tenancy(config["tenancy"]).data
    subscriptions = paginate(oci, identity.list_region_subscriptions, config["tenancy"])
    home_region = next((x.region_name for x in subscriptions if x.is_home_region), None)
    compartments = [tenancy]
    compartments.extend(
        paginate(
            oci,
            identity.list_compartments,
            config["tenancy"],
            compartment_id_in_subtree=True,
            access_level="ACCESSIBLE",
            lifecycle_state="ACTIVE",
        )
    )
    unique_compartments = {x.id: x for x in compartments}
    report: dict[str, Any] = {
        "profile": profile,
        "tenancy_name": tenancy.name,
        "tenancy_ocid_suffix": suffix(tenancy.id),
        "home_region": home_region,
        "profile_region": config["region"],
        "subscribed_regions": [x.region_name for x in subscriptions],
        "compartments_checked": len(unique_compartments),
        "config_mode": file_mode(config_file),
        "key_mode": file_mode(key_path),
        "regions": [],
        "errors": [],
    }

    for subscription in subscriptions:
        region_config = dict(config)
        region_config["region"] = subscription.region_name
        region: dict[str, Any] = {
            "name": subscription.region_name,
            "availability_domains": [],
            "compute_limits": [],
            "instances": [],
            "terminated_instances_omitted": 0,
            "reserved_public_ips": [],
        }
        try:
            regional_identity = oci.identity.IdentityClient(region_config)
            region["availability_domains"] = [
                x.name
                for x in paginate(
                    oci, regional_identity.list_availability_domains, config["tenancy"]
                )
            ]
            limits = oci.limits.LimitsClient(region_config)
            limit_values = paginate(
                oci, limits.list_limit_values, config["tenancy"], "compute"
            )
            for value in limit_values:
                if not relevant_compute_limit(value.name):
                    continue
                kwargs = {}
                if value.scope_type == "AD":
                    kwargs["availability_domain"] = value.availability_domain
                availability = limits.get_resource_availability(
                    "compute", value.name, config["tenancy"], **kwargs
                ).data
                region["compute_limits"].append(
                    {
                        "name": value.name,
                        "scope": value.scope_type,
                        "availability_domain": value.availability_domain,
                        "limit": value.value,
                        "used": availability.used,
                        "available": availability.available,
                        "fractional_used": availability.fractional_usage,
                        "fractional_available": availability.fractional_availability,
                        "effective_quota": availability.effective_quota_value,
                    }
                )

            compute = oci.core.ComputeClient(region_config)
            network = oci.core.VirtualNetworkClient(region_config)
            block = oci.core.BlockstorageClient(region_config)
            for compartment in unique_compartments.values():
                instances = paginate(oci, compute.list_instances, compartment.id)
                for instance in instances:
                    if instance.lifecycle_state == "TERMINATED" and not include_terminated:
                        region["terminated_instances_omitted"] += 1
                        continue
                    region["instances"].append(
                        collect_instance(oci, compute, network, block, instance)
                    )
                try:
                    public_ips = paginate(
                        oci,
                        network.list_public_ips,
                        "REGION",
                        compartment_id=compartment.id,
                        lifetime="RESERVED",
                    )
                    for public_ip in public_ips:
                        region["reserved_public_ips"].append(
                            {
                                "name": public_ip.display_name,
                                "ocid_suffix": suffix(public_ip.id),
                                "ip_address": public_ip.ip_address,
                                "state": public_ip.lifecycle_state,
                                "assigned_private_ip_ocid_suffix": suffix(public_ip.private_ip_id),
                            }
                        )
                except Exception as exc:
                    report["errors"].append(
                        {
                            "region": subscription.region_name,
                            "operation": "list_reserved_public_ips",
                            "compartment_ocid_suffix": suffix(compartment.id),
                            **api_error(exc),
                        }
                    )
        except Exception as exc:
            report["errors"].append(
                {
                    "region": subscription.region_name,
                    "operation": "collect_region",
                    **api_error(exc),
                }
            )
        report["regions"].append(region)
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", action="append", required=True)
    parser.add_argument("--config-file", type=Path, default=Path("~/.oci/config").expanduser())
    parser.add_argument("--include-terminated", action="store_true")
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        import oci
    except ImportError:
        print("error: install the official OCI Python SDK (python -m pip install oci)", file=sys.stderr)
        return 2
    try:
        report = {
            "read_only": True,
            "generated_at": __import__("datetime").datetime.now(
                __import__("datetime").timezone.utc
            ).isoformat(),
            "accounts": [
                collect_profile(oci, args.config_file.resolve(), profile, args.include_terminated)
                for profile in args.profile
            ],
        }
        rendered = json.dumps(report, ensure_ascii=False, indent=2)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered + "\n", encoding="utf-8")
            args.output.chmod(0o600)
        else:
            print(rendered)
        return 0
    except Exception as exc:
        print(json.dumps({"error": api_error(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
