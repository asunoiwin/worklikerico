from __future__ import annotations

import copy
import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("validate_config", ROOT / "scripts" / "validate_config.py")
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ValidateConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = json.loads((ROOT / "assets" / "default-config.json").read_text(encoding="utf-8"))

    def test_default_config_passes(self) -> None:
        self.assertEqual(MODULE.validate(self.config), [])

    def test_remote_mcp_cannot_be_enabled(self) -> None:
        changed = copy.deepcopy(self.config)
        changed["execution"]["remote_mcp"] = True
        self.assertTrue(any("remote_mcp" in item for item in MODULE.validate(changed)))

    def test_unapproved_domain_fails(self) -> None:
        changed = copy.deepcopy(self.config)
        changed["legal_sources"]["allowed_domains"].append("example.com")
        self.assertTrue(any("unapproved" in item for item in MODULE.validate(changed)))

    def test_external_send_approval_cannot_be_disabled(self) -> None:
        changed = copy.deepcopy(self.config)
        changed["approvals"]["external_send"] = False
        self.assertTrue(any("external_send" in item for item in MODULE.validate(changed)))

    def test_intake_fields_are_mandatory(self) -> None:
        changed = copy.deepcopy(self.config)
        changed["intake"]["required_fields"].remove("party_position")
        self.assertTrue(any("intake.required_fields" in item for item in MODULE.validate(changed)))

    def test_unknown_nested_key_fails(self) -> None:
        changed = copy.deepcopy(self.config)
        changed["execution"]["quietly_allow_upload"] = True
        self.assertTrue(any("unknown execution keys" in item for item in MODULE.validate(changed)))

    def test_risk_and_playbook_cannot_be_hollowed_out(self) -> None:
        changed = copy.deepcopy(self.config)
        changed["risk"]["severity_levels"] = []
        changed["risk"]["lawyer_review_topics"] = []
        changed["playbook"]["layers"] = ["one", "two", "three", "four", "five", "six"]
        errors = MODULE.validate(changed)
        self.assertTrue(any("severity_levels" in item for item in errors))
        self.assertTrue(any("lawyer_review_topics" in item for item in errors))
        self.assertTrue(any("playbook.layers" in item for item in errors))

    def test_safety_limits_cannot_be_relaxed(self) -> None:
        changed = copy.deepcopy(self.config)
        changed["document_limits"]["max_zip_entries"] = 10**12
        changed["document_limits"]["max_zip_uncompressed_bytes"] = 10**18
        changed["document_limits"]["low_text_chars_per_page"] = 0
        changed["matter"]["retain_temp_hours"] = 1
        errors = MODULE.validate(changed)
        self.assertTrue(any("max_zip_entries" in item for item in errors))
        self.assertTrue(any("max_zip_uncompressed_bytes" in item for item in errors))
        self.assertTrue(any("low_text_chars_per_page" in item for item in errors))
        self.assertTrue(any("retain_temp_hours" in item for item in errors))

    def test_mandatory_lawyer_topics_cannot_be_replaced(self) -> None:
        changed = copy.deepcopy(self.config)
        changed["risk"]["lawyer_review_topics"] = ["pretend_review"]
        self.assertTrue(any("lawyer_review_topics" in item for item in MODULE.validate(changed)))

    def test_output_types_cannot_be_extended_or_defaulted_to_signature_copy(self) -> None:
        changed = copy.deepcopy(self.config)
        changed["outputs"]["allowed_types"].append("auto_send_clean_copy")
        changed["outputs"]["default_type"] = "signature_candidate"
        errors = MODULE.validate(changed)
        self.assertTrue(any("default_type" in item for item in errors))
        self.assertTrue(any("allowed_types" in item for item in errors))

    def test_malformed_lists_are_rejected_without_crashing(self) -> None:
        changed = copy.deepcopy(self.config)
        changed["risk"]["lawyer_review_topics"] = [{}]
        changed["outputs"]["allowed_types"] = [{}]
        changed["legal_sources"]["required_evidence_fields"] = [{}]
        errors = MODULE.validate(changed)
        self.assertTrue(any("lawyer_review_topics" in item for item in errors))
        self.assertTrue(any("allowed_types" in item for item in errors))
        self.assertTrue(any("required_evidence_fields" in item for item in errors))


if __name__ == "__main__":
    unittest.main()
