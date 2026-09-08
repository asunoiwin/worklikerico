from __future__ import annotations

import importlib.util
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("inspect_contract", ROOT / "scripts" / "inspect_contract.py")
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


CONTENT_TYPES = b"""<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
</Types>"""

ROOT_RELS = b"""<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""

DOCUMENT = b"""<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body><w:p>
    <w:ins><w:r><w:t>added</w:t></w:r></w:ins>
    <w:del><w:r><w:delText>removed</w:delText></w:r></w:del>
    <w:commentRangeStart w:id="0"/>
    <w:r><w:rPr><w:vanish/><w:color w:val="FFFFFF"/></w:rPr><w:t>hidden</w:t></w:r>
    <w:fldSimple w:instr="DATE"/>
  </w:p></w:body>
</w:document>"""

COMMENTS = b"""<?xml version="1.0" encoding="UTF-8"?>
<w:comments xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:comment w:id="0"><w:p><w:r><w:t>review note</w:t></w:r></w:p></w:comment>
</w:comments>"""

DOCUMENT_RELS = b"""<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" Target="https://invalid.example/" TargetMode="External"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/oleObject" Target="embeddings/item.bin"/>
</Relationships>"""


def make_docx(path: Path, *, suspicious: bool = False, active: bool = True) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        archive.writestr("_rels/.rels", ROOT_RELS)
        archive.writestr("word/document.xml", DOCUMENT)
        archive.writestr("word/comments.xml", COMMENTS)
        archive.writestr("word/_rels/document.xml.rels", DOCUMENT_RELS)
        archive.writestr("word/embeddings/item.bin", b"opaque")
        if active:
            archive.writestr("word/vbaProject.bin", b"not executed")
        if suspicious:
            archive.writestr("../escaped.txt", b"must remain in archive")


class InspectContractTests(unittest.TestCase):
    def test_docx_reports_revisions_comments_hidden_and_container_risks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sensitive-name.docx"
            make_docx(path)
            report = MODULE.inspect_file(path)
            codes = {item["code"] for item in report["issues"]}
            self.assertEqual(report["status"], "warn")
            self.assertTrue({
                "DOCX_TRACKED_CHANGES",
                "DOCX_COMMENTS",
                "DOCX_HIDDEN_TEXT",
                "DOCX_EXTERNAL_RELATIONSHIP",
                "DOCX_EMBEDDED_OBJECT",
                "DOCX_ACTIVE_CONTENT",
            }.issubset(codes))
            self.assertEqual(report["metrics"]["tracked_change_markers"], 2)
            self.assertFalse(report["privacy"]["content_included"])
            self.assertNotIn("sensitive-name", str(report))
            self.assertNotIn("review note", str(report))
            self.assertNotIn("invalid.example", str(report))

    def test_unsafe_zip_path_is_reported_but_never_extracted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "unsafe.docx"
            make_docx(path, suspicious=True)
            outside = root.parent / "escaped.txt"
            existed_before = outside.exists()
            report = MODULE.inspect_file(path)
            codes = {item["code"] for item in report["issues"]}
            self.assertEqual(report["status"], "fail")
            self.assertIn("DOCX_SUSPICIOUS_ZIP_PATH", codes)
            self.assertEqual(outside.exists(), existed_before)

    def test_unsupported_extension_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "contract.txt"
            path.write_text("local only", encoding="utf-8")
            report = MODULE.inspect_file(path)
            self.assertEqual(report["status"], "fail")
            self.assertEqual(report["issues"][0]["code"], "UNSUPPORTED_FORMAT")

    def test_xml_entity_declaration_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "entity.docx"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("[Content_Types].xml", CONTENT_TYPES)
                archive.writestr("_rels/.rels", ROOT_RELS)
                archive.writestr("word/document.xml", b"<!DOCTYPE x [<!ENTITY e SYSTEM 'file:///etc/passwd'>]><x>&e;</x>")
            report = MODULE.inspect_file(path)
            self.assertEqual(report["status"], "fail")
            self.assertIn("DOCX_UNSAFE_XML_DECLARATION", {item["code"] for item in report["issues"]})

    def test_late_xml_entity_declaration_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "late-entity.docx"
            payload = b" " * 5000 + b"<!ENTITY late SYSTEM 'file:///etc/passwd'><x/>"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("[Content_Types].xml", CONTENT_TYPES)
                archive.writestr("_rels/.rels", ROOT_RELS)
                archive.writestr("word/document.xml", payload)
            report = MODULE.inspect_file(path)
            self.assertEqual(report["status"], "fail")
            self.assertIn("DOCX_UNSAFE_XML_DECLARATION", {item["code"] for item in report["issues"]})

    def test_zip_limit_stops_before_xml_parsing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "too-many.docx"
            make_docx(path)
            with mock.patch.object(MODULE, "_xml_root", side_effect=AssertionError("parser must not run")):
                report = MODULE.inspect_file(path, {"max_zip_entries": 1})
            self.assertEqual(report["status"], "fail")
            self.assertIn("DOCX_ZIP_ENTRY_LIMIT", {item["code"] for item in report["issues"]})

    def test_inherited_hidden_style_is_reported(self) -> None:
        styles = b"""<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:style w:type="character" w:styleId="HiddenBase"><w:rPr><w:vanish/></w:rPr></w:style>
          <w:style w:type="character" w:styleId="HiddenChild"><w:basedOn w:val="HiddenBase"/></w:style>
        </w:styles>"""
        document = b"""<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:body><w:p><w:r><w:rPr><w:rStyle w:val="HiddenChild"/></w:rPr><w:t>not reported</w:t></w:r></w:p></w:body>
        </w:document>"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "hidden-style.docx"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("[Content_Types].xml", CONTENT_TYPES)
                archive.writestr("_rels/.rels", ROOT_RELS)
                archive.writestr("word/document.xml", document)
                archive.writestr("word/styles.xml", styles)
            report = MODULE.inspect_file(path)
            self.assertEqual(report["metrics"]["hidden_style_references"], 1)
            self.assertIn("DOCX_HIDDEN_TEXT", {item["code"] for item in report["issues"]})

    @unittest.skipUnless(importlib.util.find_spec("pypdf"), "local pypdf is not installed")
    def test_pdf_is_inspected_locally_without_content_in_report(self) -> None:
        from pypdf import PdfWriter

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "confidential.pdf"
            writer = PdfWriter()
            writer.add_blank_page(width=612, height=792)
            writer.add_metadata({"/Title": "private title"})
            with path.open("wb") as handle:
                writer.write(handle)
            report = MODULE.inspect_file(path)
            self.assertEqual(report["format"], "pdf")
            self.assertEqual(report["status"], "warn")
            self.assertEqual(report["metrics"]["pages"], 1)
            self.assertIn("PDF_LOW_TEXT_PAGES", {item["code"] for item in report["issues"]})
            self.assertNotIn("private title", str(report))
            self.assertNotIn("confidential", str(report))


if __name__ == "__main__":
    unittest.main()
