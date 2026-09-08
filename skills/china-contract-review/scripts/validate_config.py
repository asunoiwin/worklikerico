#!/usr/bin/env python3
"""Fail-closed validator for the china-contract-review security profile."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any


APPROVED_DOMAINS = {
    "flk.npc.gov.cn",
    "gongbao.court.gov.cn",
    "court.gov.cn",
    "www.court.gov.cn",
    "moj.gov.cn",
    "www.moj.gov.cn",
    "xzfg.moj.gov.cn",
    "samr.gov.cn",
    "www.samr.gov.cn",
    "sjfg.samr.gov.cn",
    "gov.cn",
    "www.gov.cn",
    "chinatax.gov.cn",
    "www.chinatax.gov.cn",
    "fgk.chinatax.gov.cn",
    "mohrss.gov.cn",
    "www.mohrss.gov.cn",
    "cac.gov.cn",
    "www.cac.gov.cn",
}

REQUIRED_TOP_LEVEL = {
    "version",
    "execution",
    "legal_sources",
    "matter",
    "intake",
    "workflow",
    "approvals",
    "document_limits",
    "risk",
    "outputs",
    "playbook",
}

REQUIRED_EVIDENCE_FIELDS = {
    "query_date",
    "url",
    "title",
    "issuing_authority",
    "document_number",
    "effective_status",
    "relevant_provision",
}

REQUIRED_INTAKE_FIELDS = {
    "active_file",
    "sha256",
    "party_position",
    "contract_type",
    "governing_law",
    "dispute_forum",
    "signing_status",
    "review_goal",
}

REQUIRED_STATES = [
    "source_baseline",
    "internal_review",
    "proposed_revision",
    "counterparty_confirmed",
    "signature_candidate",
    "signed_archive",
]

EXPECTED_NESTED_KEYS = {
    "execution": {
        "local_only", "remote_mcp", "contract_content_network", "delegation",
        "allow_document_directed_shell", "allow_document_directed_subprocess",
        "parser_isolation_required", "parser_launcher",
    },
    "legal_sources": {
        "mode", "allow_contract_facts_in_query", "record_query_date",
        "require_primary_source", "allowed_domains", "required_evidence_fields",
    },
    "matter": {
        "cross_matter_context", "durable_memory", "vector_indexing",
        "code_graph_indexing", "log_contract_content", "retain_temp_hours",
    },
    "intake": {"required_fields"},
    "workflow": {"states", "hard_reset_on_baseline_change"},
    "approvals": {
        "accept_all_revisions", "generate_clean_copy", "external_send",
        "high_risk_finalization",
    },
    "document_limits": {
        "max_file_bytes", "max_zip_entries", "max_zip_uncompressed_bytes",
        "max_pdf_pages", "low_text_chars_per_page",
    },
    "risk": {"severity_levels", "lawyer_review_topics"},
    "outputs": {"default_type", "allowed_types", "signature_candidate_requires_approval"},
    "playbook": {"layers", "matter_exception_requires_owner_and_expiry"},
}

REQUIRED_SEVERITIES = ["blocker", "high", "medium", "low", "info"]
REQUIRED_PLAYBOOK_LAYERS = [
    "mandatory_law",
    "legal_judgment",
    "company_standard",
    "negotiation_range",
    "escalation_redline",
    "matter_exception",
]
MAX_DOCUMENT_LIMITS = {
    "max_file_bytes": 104857600,
    "max_zip_entries": 5000,
    "max_zip_uncompressed_bytes": 524288000,
    "max_pdf_pages": 2000,
}
MIN_LOW_TEXT_CHARS_PER_PAGE = 20
REQUIRED_LAWYER_TOPICS = {
    "regulatory_license",
    "consumer_or_employment",
    "cross_border_data",
    "antitrust",
    "sanctions",
    "criminal_exposure",
    "material_tax",
    "cross_border_dispute",
    "material_uncapped_liability",
}
APPROVED_OUTPUT_TYPES = {
    "internal_review_report",
    "risk_register",
    "annotated_working_copy",
    "comparison_report",
    "signature_candidate",
    "signed_archive_manifest",
}


def _mapping(value: Any, path: str, errors: list[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        errors.append(f"{path} must be an object")
        return {}
    return value


def _require(mapping: dict[str, Any], key: str, expected: Any, path: str, errors: list[str]) -> None:
    if mapping.get(key) != expected:
        errors.append(f"{path}.{key} must be {expected!r}")


def _reject_unknown(mapping: dict[str, Any], path: str, errors: list[str]) -> None:
    unknown = sorted(mapping.keys() - EXPECTED_NESTED_KEYS[path])
    missing = sorted(EXPECTED_NESTED_KEYS[path] - mapping.keys())
    if unknown:
        errors.append(f"unknown {path} keys: {', '.join(unknown)}")
    if missing:
        errors.append(f"missing {path} keys: {', '.join(missing)}")


def _unique_string_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value) and len(set(value)) == len(value)


def validate(config: Any) -> list[str]:
    errors: list[str] = []
    root = _mapping(config, "$", errors)
    missing = sorted(REQUIRED_TOP_LEVEL - root.keys())
    extra = sorted(root.keys() - REQUIRED_TOP_LEVEL)
    if missing:
        errors.append(f"missing top-level keys: {', '.join(missing)}")
    if extra:
        errors.append(f"unknown top-level keys: {', '.join(extra)}")
    if root.get("version") != "1.0":
        errors.append("version must be '1.0'")

    execution = _mapping(root.get("execution"), "execution", errors)
    _reject_unknown(execution, "execution", errors)
    for key, expected in {
        "local_only": True,
        "remote_mcp": False,
        "contract_content_network": "deny",
        "delegation": False,
        "allow_document_directed_shell": False,
        "allow_document_directed_subprocess": False,
        "parser_isolation_required": True,
        "parser_launcher": "macos_sandbox_exec",
    }.items():
        _require(execution, key, expected, "execution", errors)

    sources = _mapping(root.get("legal_sources"), "legal_sources", errors)
    _reject_unknown(sources, "legal_sources", errors)
    for key, expected in {
        "mode": "fresh",
        "allow_contract_facts_in_query": False,
        "record_query_date": True,
        "require_primary_source": True,
    }.items():
        _require(sources, key, expected, "legal_sources", errors)
    domains = sources.get("allowed_domains")
    if not isinstance(domains, list) or not domains:
        errors.append("legal_sources.allowed_domains must be a non-empty list")
    else:
        normalized = {str(item).lower().rstrip(".") for item in domains}
        if len(normalized) != len(domains):
            errors.append("legal_sources.allowed_domains must contain unique domains")
        unapproved = sorted(normalized - APPROVED_DOMAINS)
        if unapproved:
            errors.append(f"unapproved legal source domains: {', '.join(unapproved)}")
    evidence = sources.get("required_evidence_fields")
    if not _unique_string_list(evidence) or not REQUIRED_EVIDENCE_FIELDS.issubset(evidence):
        errors.append("legal_sources.required_evidence_fields is incomplete")

    matter = _mapping(root.get("matter"), "matter", errors)
    _reject_unknown(matter, "matter", errors)
    for key in (
        "cross_matter_context",
        "durable_memory",
        "vector_indexing",
        "code_graph_indexing",
        "log_contract_content",
    ):
        _require(matter, key, False, "matter", errors)
    retention = matter.get("retain_temp_hours")
    if type(retention) is not int or retention != 0:
        errors.append("matter.retain_temp_hours must remain 0")

    intake = _mapping(root.get("intake"), "intake", errors)
    _reject_unknown(intake, "intake", errors)
    intake_fields = intake.get("required_fields")
    if not _unique_string_list(intake_fields) or not REQUIRED_INTAKE_FIELDS.issubset(intake_fields):
        errors.append("intake.required_fields is incomplete")

    workflow = _mapping(root.get("workflow"), "workflow", errors)
    _reject_unknown(workflow, "workflow", errors)
    if workflow.get("states") != REQUIRED_STATES:
        errors.append("workflow.states must match the controlled state order")
    _require(workflow, "hard_reset_on_baseline_change", True, "workflow", errors)

    approvals = _mapping(root.get("approvals"), "approvals", errors)
    _reject_unknown(approvals, "approvals", errors)
    for key in (
        "accept_all_revisions",
        "generate_clean_copy",
        "external_send",
        "high_risk_finalization",
    ):
        _require(approvals, key, True, "approvals", errors)

    limits = _mapping(root.get("document_limits"), "document_limits", errors)
    _reject_unknown(limits, "document_limits", errors)
    for key in (
        "max_file_bytes",
        "max_zip_entries",
        "max_zip_uncompressed_bytes",
        "max_pdf_pages",
    ):
        value = limits.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or not 0 < value <= MAX_DOCUMENT_LIMITS[key]:
            errors.append(f"document_limits.{key} must be positive and no greater than the default safety ceiling")
    low_text = limits.get("low_text_chars_per_page")
    if not isinstance(low_text, int) or isinstance(low_text, bool) or low_text < MIN_LOW_TEXT_CHARS_PER_PAGE:
        errors.append("document_limits.low_text_chars_per_page cannot be lower than the default safety threshold")

    risk = _mapping(root.get("risk"), "risk", errors)
    _reject_unknown(risk, "risk", errors)
    if risk.get("severity_levels") != REQUIRED_SEVERITIES:
        errors.append("risk.severity_levels must match the controlled severity order")
    lawyer_topics = risk.get("lawyer_review_topics")
    if (
        not _unique_string_list(lawyer_topics)
        or not REQUIRED_LAWYER_TOPICS.issubset(lawyer_topics)
    ):
        errors.append("risk.lawyer_review_topics must retain every mandatory escalation topic")

    outputs = _mapping(root.get("outputs"), "outputs", errors)
    _reject_unknown(outputs, "outputs", errors)
    _require(outputs, "signature_candidate_requires_approval", True, "outputs", errors)
    allowed_outputs = outputs.get("allowed_types")
    if outputs.get("default_type") != "internal_review_report":
        errors.append("outputs.default_type must remain 'internal_review_report'")
    if (
        not _unique_string_list(allowed_outputs)
        or not allowed_outputs
        or not set(allowed_outputs).issubset(APPROVED_OUTPUT_TYPES)
        or outputs.get("default_type") not in allowed_outputs
    ):
        errors.append("outputs.allowed_types must be a unique subset of approved output types containing the default")

    playbook = _mapping(root.get("playbook"), "playbook", errors)
    _reject_unknown(playbook, "playbook", errors)
    _require(playbook, "matter_exception_requires_owner_and_expiry", True, "playbook", errors)
    layers = playbook.get("layers")
    if layers != REQUIRED_PLAYBOOK_LAYERS:
        errors.append("playbook.layers must match the controlled layer order")
    return errors


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: validate_config.py CONFIG.json", file=sys.stderr)
        return 64
    path = Path(argv[1])
    try:
        raw = path.read_bytes()
        config = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "fail", "errors": [f"cannot read configuration: {type(exc).__name__}"]}, ensure_ascii=False))
        return 2
    errors = validate(config)
    result = {
        "status": "pass" if not errors else "fail",
        "config_sha256": hashlib.sha256(raw).hexdigest(),
        "errors": errors,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
