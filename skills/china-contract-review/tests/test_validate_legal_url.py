from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("validate_legal_url", ROOT / "scripts" / "validate_legal_url.py")
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ValidateLegalUrlTests(unittest.TestCase):
    def setUp(self) -> None:
        self.allowed = {"flk.npc.gov.cn", "www.gov.cn"}

    def test_official_https_url_passes(self) -> None:
        self.assertIsNone(MODULE.validate_url("https://flk.npc.gov.cn/search", self.allowed))

    def test_http_credentials_port_and_unlisted_subdomain_fail(self) -> None:
        cases = [
            "http://flk.npc.gov.cn/search",
            "https://user@flk.npc.gov.cn/search",
            "https://flk.npc.gov.cn:8443/search",
            "https://evil.gov.cn/search",
        ]
        for url in cases:
            with self.subTest(url=url):
                self.assertIsNotNone(MODULE.validate_url(url, self.allowed))


if __name__ == "__main__":
    unittest.main()
