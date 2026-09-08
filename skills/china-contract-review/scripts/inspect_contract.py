#!/usr/bin/env python3
"""Read-only structural preflight for DOCX and PDF contract files.

The report intentionally excludes filenames, paths, document text, metadata values,
relationship targets, and annotation contents.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import posixpath
import re
import sys
import zipfile
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any
from xml.etree import ElementTree as ET


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CP_NS = "http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
DC_NS = "http://purl.org/dc/elements/1.1/"
DCTERMS_NS = "http://purl.org/dc/terms/"

DEFAULT_LIMITS = {
    "max_file_bytes": 100 * 1024 * 1024,
    "max_zip_entries": 5000,
    "max_zip_uncompressed_bytes": 500 * 1024 * 1024,
    "max_pdf_pages": 2000,
    "low_text_chars_per_page": 20,
    "max_xml_part_bytes": 25 * 1024 * 1024,
}


class UnsafeXmlDeclaration(ValueError):
    pass

TRACKED_TAGS = {
    "ins",
    "del",
    "moveFrom",
    "moveTo",
    "rPrChange",
    "pPrChange",
    "tblPrChange",
    "tblGridChange",
    "trPrChange",
    "tcPrChange",
    "sectPrChange",
    "numberingChange",
}
STORY_PREFIXES = (
    "word/document.xml",
    "word/header",
    "word/footer",
    "word/footnotes.xml",
    "word/endnotes.xml",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _issue(code: str, severity: str, message: str, count: int = 1) -> dict[str, Any]:
    return {"code": code, "severity": severity, "message": message, "count": count}


def _status(issues: list[dict[str, Any]]) -> str:
    severities = {item["severity"] for item in issues}
    if severities & {"critical", "error"}:
        return "fail"
    if "partial" in severities:
        return "partial"
    if "warning" in severities:
        return "warn"
    return "pass"


def _safe_zip_name(name: str) -> bool:
    if not name or "\\" in name or name.startswith("/") or re.match(r"^[A-Za-z]:", name):
        return False
    parts = PurePosixPath(name).parts
    return ".." not in parts and all(part not in ("", ".") for part in parts)


def _xml_root(data: bytes) -> ET.Element:
    if re.search(br"<!\s*(?:DOCTYPE|ENTITY)\b", data, flags=re.IGNORECASE):
        raise UnsafeXmlDeclaration("DTD or entity declaration is not allowed")
    return ET.fromstring(data)


def _read_zip_part(archive: zipfile.ZipFile, info: zipfile.ZipInfo, limit: int) -> bytes:
    with archive.open(info, "r") as handle:
        data = handle.read(limit + 1)
    if len(data) > limit:
        raise OverflowError("ZIP part exceeds read limit")
    return data


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _relationship_base(rels_name: str) -> str:
    if rels_name == "_rels/.rels":
        return ""
    marker = "/_rels/"
    if marker not in rels_name or not rels_name.endswith(".rels"):
        return ""
    prefix, leaf = rels_name.split(marker, 1)
    source = posixpath.join(prefix, leaf[:-5])
    return posixpath.dirname(source)


def _resolve_relationship(rels_name: str, target: str) -> str:
    clean = target.split("#", 1)[0]
    return posixpath.normpath(posixpath.join(_relationship_base(rels_name), clean)).lstrip("/")


def inspect_docx(path: Path, limits: dict[str, int]) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    metrics: Counter[str] = Counter()
    try:
        archive = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError):
        issues.append(_issue("DOCX_INVALID_CONTAINER", "error", "File is not a readable DOCX ZIP container."))
        return {"format": "docx", "metrics": dict(metrics), "issues": issues}

    with archive:
        infos = archive.infolist()
        names = [info.filename for info in infos]
        name_set = set(names)
        metrics["zip_entries"] = len(infos)
        metrics["zip_uncompressed_bytes"] = sum(info.file_size for info in infos)
        duplicate_count = len(names) - len(name_set)
        suspicious_count = sum(not _safe_zip_name(name) for name in names)
        if len(infos) > limits["max_zip_entries"]:
            issues.append(_issue("DOCX_ZIP_ENTRY_LIMIT", "error", "DOCX exceeds the configured ZIP entry limit.", len(infos)))
        if metrics["zip_uncompressed_bytes"] > limits["max_zip_uncompressed_bytes"]:
            issues.append(_issue("DOCX_ZIP_SIZE_LIMIT", "error", "DOCX exceeds the configured uncompressed-size limit.", metrics["zip_uncompressed_bytes"]))
        if duplicate_count:
            issues.append(_issue("DOCX_DUPLICATE_ZIP_ENTRY", "warning", "DOCX contains duplicate ZIP entry names.", duplicate_count))
        if suspicious_count:
            issues.append(_issue("DOCX_SUSPICIOUS_ZIP_PATH", "error", "DOCX contains unsafe archive paths; nothing was extracted.", suspicious_count))

        required = {"[Content_Types].xml", "_rels/.rels", "word/document.xml"}
        missing_required = sorted(required - name_set)
        if missing_required:
            issues.append(_issue("DOCX_MISSING_PART", "error", "DOCX is missing required package parts.", len(missing_required)))
        if any(item["severity"] == "error" for item in issues):
            return {"format": "docx", "metrics": dict(metrics), "issues": issues}

        macro_count = sum(name.lower().endswith("vbaproject.bin") or "activex/" in name.lower() for name in names)
        embedded_count = sum("/embeddings/" in name.lower() or name.lower().endswith("oleobject.bin") for name in names)
        signature_count = sum(name.lower().startswith("_xmlsignatures/") for name in names)
        custom_xml_count = sum(name.lower().startswith("customxml/") and name.lower().endswith(".xml") for name in names)
        altchunk_count = sum("altchunk" in name.lower() for name in names)
        metrics.update(
            {
                "macro_or_activex_parts": macro_count,
                "embedded_object_parts": embedded_count,
                "digital_signature_parts": signature_count,
                "custom_xml_parts": custom_xml_count,
                "altchunk_parts": altchunk_count,
                "media_parts": sum(name.lower().startswith("word/media/") for name in names),
                "header_footer_parts": sum(name.lower().startswith(("word/header", "word/footer")) and name.lower().endswith(".xml") for name in names),
            }
        )
        if macro_count:
            issues.append(_issue("DOCX_ACTIVE_CONTENT", "warning", "DOCX contains macro or ActiveX parts; they were not executed.", macro_count))
        if embedded_count:
            issues.append(_issue("DOCX_EMBEDDED_OBJECT", "warning", "DOCX contains embedded objects; they were not opened.", embedded_count))
        if signature_count:
            issues.append(_issue("DOCX_DIGITAL_SIGNATURE", "warning", "DOCX contains signature parts; presence does not prove validity.", signature_count))
        if altchunk_count:
            issues.append(_issue("DOCX_ALTCHUNK", "warning", "DOCX contains alternative-format import parts.", altchunk_count))

        xml_names = [
            name
            for name in names
            if name.lower().endswith((".xml", ".rels")) and _safe_zip_name(name)
        ]
        parsed_roots: dict[str, ET.Element] = {}
        parse_failures = 0
        rejected_xml = 0
        unsafe_xml = 0
        for name in xml_names:
            try:
                info = archive.getinfo(name)
                if info.file_size > limits["max_xml_part_bytes"]:
                    rejected_xml += 1
                    continue
                parsed_roots[name] = _xml_root(_read_zip_part(archive, info, limits["max_xml_part_bytes"]))
            except OverflowError:
                rejected_xml += 1
            except UnsafeXmlDeclaration:
                unsafe_xml += 1
            except (KeyError, OSError, ET.ParseError, ValueError, RuntimeError):
                parse_failures += 1
        if rejected_xml:
            issues.append(_issue("DOCX_XML_PART_LIMIT", "partial", "One or more XML parts exceeded the per-part read limit.", rejected_xml))
        if parse_failures:
            issues.append(_issue("DOCX_XML_PARSE_FAILURE", "partial", "One or more XML parts could not be safely parsed.", parse_failures))
        if unsafe_xml:
            issues.append(_issue("DOCX_UNSAFE_XML_DECLARATION", "error", "DOCX contains forbidden DTD or entity declarations.", unsafe_xml))

        external_relationships = 0
        missing_targets = 0
        attachment_relationships = 0
        hyperlink_relationships = 0
        for rels_name, root in parsed_roots.items():
            if not rels_name.endswith(".rels"):
                continue
            for rel in root.iter():
                if _local(rel.tag) != "Relationship":
                    continue
                target_mode = rel.attrib.get("TargetMode", "")
                target = rel.attrib.get("Target", "")
                rel_type = rel.attrib.get("Type", "").lower()
                if target_mode.lower() == "external":
                    external_relationships += 1
                elif target:
                    resolved = _resolve_relationship(rels_name, target)
                    if resolved not in name_set:
                        missing_targets += 1
                if any(token in rel_type for token in ("oleobject", "package", "attachedtemplate")):
                    attachment_relationships += 1
                if "hyperlink" in rel_type:
                    hyperlink_relationships += 1
        metrics["external_relationships"] = external_relationships
        metrics["missing_internal_relationship_targets"] = missing_targets
        metrics["attachment_relationships"] = attachment_relationships
        metrics["hyperlink_relationships"] = hyperlink_relationships
        if external_relationships:
            issues.append(_issue("DOCX_EXTERNAL_RELATIONSHIP", "warning", "DOCX contains external relationships; targets were not opened or reported.", external_relationships))
        if missing_targets:
            issues.append(_issue("DOCX_MISSING_RELATIONSHIP_TARGET", "warning", "DOCX contains missing internal relationship targets.", missing_targets))

        hidden_style_ids: set[str] = set()
        style_parents: dict[str, str] = {}
        styles_root = parsed_roots.get("word/styles.xml")
        if styles_root is not None:
            for style in styles_root.iter(f"{{{W_NS}}}style"):
                style_id = style.attrib.get(f"{{{W_NS}}}styleId", "")
                if not style_id:
                    continue
                based_on = style.find(f"{{{W_NS}}}basedOn")
                if based_on is not None:
                    parent = based_on.attrib.get(f"{{{W_NS}}}val", "")
                    if parent:
                        style_parents[style_id] = parent
                for node in style.iter():
                    local = _local(node.tag)
                    if local in ("vanish", "webHidden"):
                        hidden_style_ids.add(style_id)
                    elif local == "color" and node.attrib.get(f"{{{W_NS}}}val", "").upper() in {"FFFFFF", "WHITE"}:
                        hidden_style_ids.add(style_id)
                    elif local == "sz":
                        try:
                            if int(node.attrib.get(f"{{{W_NS}}}val", "999")) <= 4:
                                hidden_style_ids.add(style_id)
                        except ValueError:
                            pass
            changed = True
            while changed:
                changed = False
                for style_id, parent in style_parents.items():
                    if parent in hidden_style_ids and style_id not in hidden_style_ids:
                        hidden_style_ids.add(style_id)
                        changed = True

        tracked = comments = comment_ranges = hidden = fields = text_chars = 0
        white_or_tiny_text = 0
        hidden_style_references = 0
        for name, root in parsed_roots.items():
            if name == "word/comments.xml":
                comments += sum(_local(node.tag) == "comment" for node in root.iter())
            if not name.startswith(STORY_PREFIXES):
                continue
            for node in root.iter():
                local = _local(node.tag)
                if local in TRACKED_TAGS:
                    tracked += 1
                elif local in ("commentRangeStart", "commentReference"):
                    comment_ranges += 1
                elif local in ("vanish", "webHidden"):
                    hidden += 1
                elif local in ("fldSimple", "instrText"):
                    fields += 1
                elif local == "t" and node.text:
                    text_chars += len(node.text)
                elif local == "color" and node.attrib.get(f"{{{W_NS}}}val", "").upper() in {"FFFFFF", "WHITE"}:
                    white_or_tiny_text += 1
                elif local == "sz":
                    try:
                        if int(node.attrib.get(f"{{{W_NS}}}val", "999")) <= 4:
                            white_or_tiny_text += 1
                    except ValueError:
                        pass
                elif local in ("rStyle", "pStyle") and node.attrib.get(f"{{{W_NS}}}val", "") in hidden_style_ids:
                    hidden_style_references += 1
        metrics.update(
            {
                "tracked_change_markers": tracked,
                "comments": comments,
                "comment_anchors_or_references": comment_ranges,
                "hidden_text_markers": hidden,
                "white_or_tiny_text_markers": white_or_tiny_text,
                "hidden_style_definitions": len(hidden_style_ids),
                "hidden_style_references": hidden_style_references,
                "field_code_markers": fields,
                "visible_text_character_count": text_chars,
            }
        )
        if tracked:
            issues.append(_issue("DOCX_TRACKED_CHANGES", "warning", "DOCX contains tracked-change markers.", tracked))
        if comments or comment_ranges:
            issues.append(_issue("DOCX_COMMENTS", "warning", "DOCX contains comments or comment anchors.", comments + comment_ranges))
        if hidden or white_or_tiny_text or hidden_style_references:
            issues.append(_issue("DOCX_HIDDEN_TEXT", "warning", "DOCX contains hidden, white, very small, or inherited hidden-style markers.", hidden + white_or_tiny_text + hidden_style_references))
        if fields:
            issues.append(_issue("DOCX_FIELD_CODES", "warning", "DOCX contains field-code markers; fields were not updated or executed.", fields))

        core = parsed_roots.get("docProps/core.xml")
        if core is not None:
            metadata_tags = {
                f"{{{DC_NS}}}creator",
                f"{{{CP_NS}}}lastModifiedBy",
                f"{{{CP_NS}}}revision",
                f"{{{DCTERMS_NS}}}created",
                f"{{{DCTERMS_NS}}}modified",
            }
            metrics["populated_core_metadata_fields"] = sum(node.tag in metadata_tags and bool((node.text or "").strip()) for node in core.iter())
    return {"format": "docx", "metrics": dict(metrics), "issues": issues}


def _pdf_name(value: Any) -> str:
    try:
        return str(value)
    except Exception:
        return ""


def inspect_pdf(path: Path, limits: dict[str, int]) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    metrics: Counter[str] = Counter()
    with path.open("rb") as handle:
        head = handle.read(8)
        handle.seek(0)
        raw = handle.read()
    if not head.startswith(b"%PDF-"):
        issues.append(_issue("PDF_INVALID_HEADER", "error", "File does not have a PDF header."))
        return {"format": "pdf", "metrics": dict(metrics), "issues": issues}

    token_counts = {
        "javascript_tokens": len(re.findall(rb"/JavaScript\b|/JS\b", raw)),
        "open_action_tokens": len(re.findall(rb"/OpenAction\b|/AA\b", raw)),
        "launch_tokens": len(re.findall(rb"/Launch\b", raw)),
        "embedded_file_tokens": len(re.findall(rb"/EmbeddedFiles?\b|/Filespec\b", raw)),
    }
    metrics.update(token_counts)
    if token_counts["javascript_tokens"] or token_counts["open_action_tokens"] or token_counts["launch_tokens"]:
        issues.append(_issue("PDF_ACTIVE_ACTION", "warning", "PDF contains active-action markers; no action was executed.", sum(token_counts[key] for key in ("javascript_tokens", "open_action_tokens", "launch_tokens"))))
    if token_counts["embedded_file_tokens"]:
        issues.append(_issue("PDF_EMBEDDED_FILE", "warning", "PDF contains embedded-file markers; attachments were not extracted.", token_counts["embedded_file_tokens"]))

    try:
        from pypdf import PdfReader
    except ImportError:
        issues.append(_issue("PDF_PARSER_UNAVAILABLE", "partial", "Local pypdf is unavailable; only header and static marker checks completed."))
        return {"format": "pdf", "metrics": dict(metrics), "issues": issues}

    try:
        reader = PdfReader(path, strict=False)
    except Exception:
        issues.append(_issue("PDF_PARSE_FAILURE", "error", "Local PDF parser could not read the document."))
        return {"format": "pdf", "metrics": dict(metrics), "issues": issues}

    metrics["encrypted"] = int(bool(reader.is_encrypted))
    if reader.is_encrypted:
        issues.append(_issue("PDF_ENCRYPTED", "error", "PDF is encrypted; content inspection stopped."))
        return {"format": "pdf", "metrics": dict(metrics), "issues": issues}
    try:
        page_count = len(reader.pages)
    except Exception:
        issues.append(_issue("PDF_PAGE_TREE_FAILURE", "error", "PDF page tree could not be read."))
        return {"format": "pdf", "metrics": dict(metrics), "issues": issues}
    metrics["pages"] = page_count
    if page_count > limits["max_pdf_pages"]:
        issues.append(_issue("PDF_PAGE_LIMIT", "error", "PDF exceeds the configured page limit.", page_count))
        return {"format": "pdf", "metrics": dict(metrics), "issues": issues}

    catalog_actions = embedded_name_trees = 0
    try:
        catalog = reader.trailer["/Root"].get_object()
        catalog_actions = sum(key in catalog for key in ("/OpenAction", "/AA"))
        names_object = catalog.get("/Names")
        if names_object is not None:
            names_dictionary = names_object.get_object()
            catalog_actions += int("/JavaScript" in names_dictionary)
            embedded_name_trees += int("/EmbeddedFiles" in names_dictionary)
    except Exception:
        issues.append(_issue("PDF_CATALOG_INSPECTION", "partial", "PDF catalog actions or name trees could not be completely inspected."))
    metrics["catalog_active_actions"] = catalog_actions
    metrics["embedded_file_name_trees"] = embedded_name_trees
    if catalog_actions:
        issues.append(_issue("PDF_ACTIVE_ACTION", "warning", "PDF catalog contains active actions; no action was executed.", catalog_actions))
    if embedded_name_trees:
        issues.append(_issue("PDF_EMBEDDED_FILE", "warning", "PDF catalog contains an embedded-file name tree; attachments were not extracted.", embedded_name_trees))

    low_text_pages = extraction_failures = annotations = links = signature_fields = 0
    annotation_actions = 0
    for page in reader.pages:
        try:
            text = page.extract_text() or ""
            if len(text.strip()) < limits["low_text_chars_per_page"]:
                low_text_pages += 1
        except Exception:
            extraction_failures += 1
        try:
            for annotation_ref in page.get("/Annots", []) or []:
                annotation = annotation_ref.get_object()
                annotations += 1
                if _pdf_name(annotation.get("/Subtype")) == "/Link":
                    links += 1
                action_ref = annotation.get("/A")
                if action_ref is not None:
                    action = action_ref.get_object()
                    if _pdf_name(action.get("/S")) in {"/JavaScript", "/Launch", "/URI", "/GoToR", "/SubmitForm"}:
                        annotation_actions += 1
        except Exception:
            extraction_failures += 1
    try:
        fields = reader.get_fields() or {}
        signature_fields = sum(_pdf_name(field.get("/FT")) == "/Sig" for field in fields.values())
        metrics["form_fields"] = len(fields)
    except Exception:
        extraction_failures += 1
    metrics.update(
        {
            "low_text_pages": low_text_pages,
            "text_or_structure_failures": extraction_failures,
            "annotations": annotations,
            "link_annotations": links,
            "annotation_active_actions": annotation_actions,
            "signature_fields": signature_fields,
            "populated_metadata_fields": sum(bool(value) for value in (reader.metadata or {}).values()),
        }
    )
    if low_text_pages:
        issues.append(_issue("PDF_LOW_TEXT_PAGES", "warning", "PDF contains low-text pages that require local visual or OCR review.", low_text_pages))
    if extraction_failures:
        issues.append(_issue("PDF_INCOMPLETE_EXTRACTION", "partial", "Some PDF text or structure could not be inspected.", extraction_failures))
    if annotations or links:
        issues.append(_issue("PDF_ANNOTATIONS_OR_LINKS", "warning", "PDF contains annotations or links; targets were not opened.", annotations + links))
    if annotation_actions:
        issues.append(_issue("PDF_ACTIVE_ACTION", "warning", "PDF annotations contain active actions; no action was executed.", annotation_actions))
    if signature_fields:
        issues.append(_issue("PDF_SIGNATURE_FIELD", "warning", "PDF contains signature fields; presence does not prove cryptographic validity.", signature_fields))
    return {"format": "pdf", "metrics": dict(metrics), "issues": issues}


def inspect_file(path: Path, limits: dict[str, int] | None = None) -> dict[str, Any]:
    effective = dict(DEFAULT_LIMITS)
    if limits:
        effective.update(limits)
    issues: list[dict[str, Any]] = []
    try:
        stat = path.stat()
    except OSError:
        return {"schema_version": "1.0", "status": "fail", "issues": [_issue("FILE_UNREADABLE", "error", "Input file cannot be read.")], "metrics": {}}
    if not path.is_file():
        return {"schema_version": "1.0", "status": "fail", "issues": [_issue("FILE_NOT_REGULAR", "error", "Input must be a regular file.")], "metrics": {}}
    if stat.st_size > effective["max_file_bytes"]:
        return {
            "schema_version": "1.0",
            "status": "fail",
            "sha256": _sha256(path),
            "size_bytes": stat.st_size,
            "issues": [_issue("FILE_SIZE_LIMIT", "error", "Input exceeds the configured file-size limit.", stat.st_size)],
            "metrics": {},
        }
    suffix = path.suffix.lower()
    if suffix == ".docx":
        detail = inspect_docx(path, effective)
    elif suffix == ".pdf":
        detail = inspect_pdf(path, effective)
    else:
        detail = {"format": "unsupported", "metrics": {}, "issues": [_issue("UNSUPPORTED_FORMAT", "error", "Only .docx and .pdf inputs are supported.")]}
    issues.extend(detail.pop("issues"))
    return {
        "schema_version": "1.0",
        "status": _status(issues),
        "format": detail.pop("format"),
        "sha256": _sha256(path),
        "size_bytes": stat.st_size,
        "privacy": {
            "content_included": False,
            "filename_included": False,
            "metadata_values_included": False,
            "relationship_targets_included": False,
        },
        "metrics": detail.pop("metrics"),
        "issues": issues,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only local DOCX/PDF structural preflight; JSON is written to stdout.")
    parser.add_argument("input", type=Path, help="local .docx or .pdf file")
    parser.add_argument("--max-file-bytes", type=int, default=DEFAULT_LIMITS["max_file_bytes"])
    parser.add_argument("--max-zip-entries", type=int, default=DEFAULT_LIMITS["max_zip_entries"])
    parser.add_argument("--max-zip-uncompressed-bytes", type=int, default=DEFAULT_LIMITS["max_zip_uncompressed_bytes"])
    parser.add_argument("--max-pdf-pages", type=int, default=DEFAULT_LIMITS["max_pdf_pages"])
    parser.add_argument("--low-text-chars-per-page", type=int, default=DEFAULT_LIMITS["low_text_chars_per_page"])
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    limits = {
        "max_file_bytes": args.max_file_bytes,
        "max_zip_entries": args.max_zip_entries,
        "max_zip_uncompressed_bytes": args.max_zip_uncompressed_bytes,
        "max_pdf_pages": args.max_pdf_pages,
        "low_text_chars_per_page": args.low_text_chars_per_page,
    }
    if any(value < 0 for value in limits.values()) or not all(limits[key] > 0 for key in limits if key != "low_text_chars_per_page"):
        print(json.dumps({"status": "fail", "issues": [_issue("INVALID_LIMIT", "error", "All limits must be positive, except low-text threshold may be zero.")]}))
        return 64
    report = inspect_file(args.input, limits)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return {"pass": 0, "warn": 0, "partial": 3, "fail": 2}[report["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
