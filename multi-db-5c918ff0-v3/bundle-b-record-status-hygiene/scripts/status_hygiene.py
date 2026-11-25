#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
status_hygiene.py — Record Status Hygiene & Version Reconciliation
(文献状态卫生与版本归并引擎)

Part of skill bundle "record-status-hygiene" for the Bohrium Playground
challenge "多数据库联合检索" (multi-database federated literature search).

Center of gravity: RECORD STATUS RISK in multi-source results. A merged
candidate set that silently includes a retracted paper, or counts a preprint
and its journal version-of-record (VoR) as two independent studies, is wrong
even if DOI-level dedup succeeded. This engine:

  parse     read case.json + task.md; sniff & normalize every material
            (crossref / europepmc / publisher json|jsonl|csv /
            reference_graph / import_state / unknown) into normalized.jsonl
            with explicit missing/unknown/not_provided semantics.
  scan      extract status signals per record (retractions, errata,
            expressions of concern, withdrawn flags, preprint markers) with
            machine-readable reason codes and evidence locators
            (file + jsonpath) for every signal.
  pair      preprint<->VoR pairing: explicit relation links first;
            bibliographic fallback goes to a REVIEW queue, never auto-pairs.
  reconcile import_state vs responses: withdrawn entries excluded,
            absent-but-claimed entries flagged import_inconsistent,
            unknown records noted not_yet_imported.
  adjudicate validate & apply model-authored dispositions.json.
  finalize  status_ledger.json + status_report.md + candidate_pool.json
            (version-pair folding) + result.json (full output contract).
  selfcheck contract keys, evidence locators, recomputed counts, no silent
            drops, no severe record in candidate pool. Exit 0/1.
  run-all   the whole pipeline with honest degradation.

Pure Python 3 standard library. No network, no randomness, no wall-clock in
artifacts. Deterministic (sorted scans, sorted JSON keys) and idempotent
(rerun overwrites). Exit codes:
  0  ok (status "success" or honest "partial")
  1  selfcheck failure (contract violated)
  2  honest degradation (no materials / invalid dispositions / internal
     error; partial results written where possible)
  3  invalid input (case.json missing / unreadable / not a JSON object)
"""

import argparse
import csv
import hashlib
import json
import os
import re
import sys

VERSION = "1.0.0"
SKILL_NAME = "record-status-hygiene"

# --------------------------------------------------------------------------
# Reason codes (normative table: references/status-vocabulary.md)
# severity: severe | flagged | info | warning
#   severe  -> record status_class "severe" (excluded from candidate pool)
#   flagged -> record status_class "flagged" (requires model disposition)
#   info    -> informational (preprint markers, import bookkeeping)
#   warning -> dataset-level issue (import inconsistency), not per-record
# --------------------------------------------------------------------------
REASON_SEVERITY = {
    "CROSSREF_IS_RETRACTION_OF": "severe",
    "CROSSREF_HAS_RETRACTION": "severe",
    "TARGET_RETRACTED": "severe",
    "CROSSREF_IS_ERRATUM_OF": "flagged",
    "CROSSREF_HAS_ERRATUM": "flagged",
    "TARGET_CORRECTED": "flagged",
    "CROSSREF_IS_EXPRESSION_OF_CONCERN_OF": "flagged",
    "CROSSREF_HAS_EXPRESSION_OF_CONCERN": "flagged",
    "TARGET_CONCERNED": "flagged",
    "CROSSREF_UPDATE_TO": "flagged",
    "CROSSREF_UPDATE_BY": "flagged",
    "EPMC_RETRACTION_OF_PUBLICATION": "severe",
    "EPMC_RETRACTED_PUBLICATION": "severe",
    "EPMC_ERRATUM": "flagged",
    "EPMC_EXPRESSION_OF_CONCERN": "flagged",
    "PUBLISHER_STATUS_RETRACTED": "severe",
    "PUBLISHER_STATUS_NOTICE": "flagged",
    "REFGRAPH_NODE_WITHDRAWN": "severe",
    "REFGRAPH_NODE_NOTICE": "flagged",
    "REFGRAPH_RETRACTION_EDGE": "severe",
    "STATUS_SOURCE_CONFLICT": "flagged",
    "IMPORT_STATE_WITHDRAWN": "severe",
    "IMPORT_STATE_INCONSISTENT": "warning",
    "IMPORT_NOT_YET_IMPORTED": "info",
    "CROSSREF_POSTED_CONTENT": "info",
    "CROSSREF_PREPRINT_RELATION": "info",
    "EPMC_PREPRINT": "info",
}

ALLOWED_DISPOSITIONS = {
    "exclude_as_retracted",
    "keep_with_notice",
    "keep_clean",
    "merge_version_pair",
    "split_not_same",
}

# Relation types whose presence means "this record is a notice about X".
NOTICE_RELATIONS_SEVERE = {"is-retraction-of"}
NOTICE_RELATIONS_FLAGGED = {"is-erratum-of", "is-correction-of",
                            "is-expression-of-concern-of"}
# Relation types meaning "this record is affected by a notice".
AFFECTED_RELATIONS_SEVERE = {"has-retraction"}
AFFECTED_RELATIONS_FLAGGED = {"has-erratum", "has-correction",
                              "has-expression-of-concern"}
UPDATE_RELATIONS = {"update-to": "CROSSREF_UPDATE_TO",
                    "update-by": "CROSSREF_UPDATE_BY"}
PREPRINT_RELATIONS = {"is-preprint-of", "has-preprint"}

EPMC_SEVERE_PUBTYPES = {"retraction of publication": "EPMC_RETRACTION_OF_PUBLICATION",
                        "retracted publication": "EPMC_RETRACTED_PUBLICATION"}
EPMC_FLAGGED_PUBTYPES = {"erratum": "EPMC_ERRATUM",
                         "correction": "EPMC_ERRATUM",
                         "expression of concern": "EPMC_EXPRESSION_OF_CONCERN"}

PUBLISHER_STATUS_SEVERE = {"retracted", "withdrawn", "retraction", "removed"}
PUBLISHER_STATUS_FLAGGED = {"expression_of_concern", "expression of concern",
                            "eoc", "correction", "corrected", "erratum",
                            "concern"}

GRAPH_NODE_SEVERE = {"retracted", "withdrawn", "removed"}
GRAPH_NODE_FLAGGED = {"expression_of_concern", "expression of concern",
                      "corrected", "erratum"}
GRAPH_EDGE_RETRACTION = {"retracts", "retraction", "is-retraction-of",
                         "retracted-by"}

IMPORT_WITHDRAWN_STATES = {"withdrawn", "removed", "retracted", "deleted"}


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------
def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def read_bytes(path):
    with open(path, "rb") as fh:
        return fh.read()


def write_json(path, obj):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, sort_keys=True, indent=2)
        fh.write("\n")


def write_text(path, text):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def write_jsonl(path, rows):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True))
            fh.write("\n")


def read_jsonl(path):
    rows = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def norm_doi(value):
    if not isinstance(value, str):
        return None
    v = value.strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:", "doi.org/"):
        if v.startswith(prefix):
            v = v[len(prefix):]
    v = v.strip().strip("/")
    return v or None


def norm_title(value):
    if not isinstance(value, str):
        return None
    v = value.lower()
    v = re.sub(r"<[^>]+>", " ", v)          # strip HTML residue
    v = re.sub(r"[^a-z0-9一-鿿]+", " ", v)
    v = re.sub(r"\s+", " ", v).strip()
    return v or None


def norm_surname(value):
    if not isinstance(value, str):
        return None
    v = re.sub(r"[^a-z一-鿿]+", "", value.lower())
    return v or None


def looks_like_doi(value):
    return isinstance(value, str) and value.strip().lower().startswith("10.")


def relpath(path, base):
    try:
        return os.path.relpath(path, base)
    except ValueError:
        return path


# --------------------------------------------------------------------------
# Case loading & material discovery / sniffing
# --------------------------------------------------------------------------
def load_case(input_dir):
    """Load case.json. Returns (case_dict, case_path). Exits 3 on failure."""
    case_path = os.path.join(input_dir, "case.json")
    if not os.path.isfile(case_path):
        sys.stderr.write("FATAL: case.json not found at %s\n" % case_path)
        sys.exit(3)
    try:
        data = json.loads(read_bytes(case_path).decode("utf-8-sig"))
    except Exception as exc:  # noqa: BLE001 - honest input error
        sys.stderr.write("FATAL: case.json unreadable/invalid JSON: %s\n" % exc)
        sys.exit(3)
    if not isinstance(data, dict):
        sys.stderr.write("FATAL: case.json is not a JSON object\n")
        sys.exit(3)
    return data, case_path


def discover_materials(case, input_dir):
    """Return ordered list of {path(abs), rel, role} for all materials.

    Primary source: case.json "materials". Fallback: sorted scan of the
    conventional materials/ subdirectory. Missing files are kept in the list
    with exists=False so the absence is declared, never silent.
    """
    found = []
    seen = set()
    for entry in case.get("materials") or []:
        if not isinstance(entry, dict) or not entry.get("path"):
            continue
        rel = entry["path"]
        abs_path = os.path.join(input_dir, rel)
        found.append({
            "path": abs_path,
            "rel": rel,
            "role": entry.get("role"),
            "exists": os.path.isfile(abs_path),
        })
        seen.add(os.path.normpath(abs_path))
    if not found:
        mdir = os.path.join(input_dir, "materials")
        if os.path.isdir(mdir):
            for name in sorted(os.listdir(mdir)):
                abs_path = os.path.join(mdir, name)
                if os.path.isfile(abs_path) and \
                        os.path.normpath(abs_path) not in seen:
                    found.append({
                        "path": abs_path,
                        "rel": os.path.join("materials", name),
                        "role": None,
                        "exists": True,
                    })
    found.sort(key=lambda m: m["rel"])
    return found


def sniff_material(data):
    """Classify decoded JSON/text payload by content shape."""
    if isinstance(data, dict):
        msg = data.get("message")
        if isinstance(msg, dict) and isinstance(msg.get("items"), list):
            return "crossref"
        rl = data.get("resultList")
        if isinstance(rl, dict) and isinstance(rl.get("result"), list):
            return "europepmc"
        if isinstance(data.get("nodes"), list) or isinstance(data.get("edges"), list):
            return "reference_graph"
        recs = data.get("records") or data.get("entries")
        if isinstance(recs, list) and (not recs or
                                       (isinstance(recs[0], dict) and
                                        ("db" in recs[0] or "identifier" in recs[0]))):
            return "import_state"
        return "unknown"
    if isinstance(data, list):
        if data and isinstance(data[0], dict) and \
                ("doi" in data[0] or "title" in data[0]):
            return "publisher"
        return "unknown"
    return "unknown"


def sniff_text_material(text):
    """Classify a non-JSON payload: JSONL publisher records or CSV."""
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return "unknown"
    jsonl_ok = True
    for ln in lines[:50]:
        try:
            obj = json.loads(ln)
            if not isinstance(obj, dict):
                jsonl_ok = False
                break
        except Exception:  # noqa: BLE001
            jsonl_ok = False
            break
    if jsonl_ok:
        return "publisher_jsonl"
    header = lines[0].lower()
    if "," in header and ("doi" in header or "title" in header):
        return "publisher_csv"
    return "unknown"


# --------------------------------------------------------------------------
# Normalization (parse)
# --------------------------------------------------------------------------
NOT_PROVIDED = "not_provided"


def _first_str(value):
    if isinstance(value, list) and value and isinstance(value[0], str):
        return value[0]
    if isinstance(value, str):
        return value
    return None


def _extract_year(value):
    if isinstance(value, dict):
        parts = value.get("date-parts")
        if isinstance(parts, list) and parts and isinstance(parts[0], list) \
                and parts[0] and isinstance(parts[0][0], int):
            return parts[0][0]
    if isinstance(value, str):
        m = re.match(r"(\d{4})", value.strip())
        if m:
            return int(m.group(1))
    if isinstance(value, int):
        return value
    return None


def _norm_crossref_item(item, rel, idx):
    locator = "%s::$.message.items[%d]" % (rel, idx)
    authors = []
    for a in item.get("author") or []:
        if isinstance(a, dict):
            authors.append({
                "given": a.get("given"),
                "family": a.get("family"),
                "surname_norm": norm_surname(a.get("family")),
            })
    relations = []
    for j, reln in enumerate(item.get("relation") or []):
        if isinstance(reln, dict):
            relations.append({
                "relation_type": reln.get("relation-type"),
                "id": reln.get("id"),
                "id_type": reln.get("id-type"),
                "locator": "%s.relation[%d]" % (locator, j),
            })
    for j, reln in enumerate(item.get("update-to") or []):
        if isinstance(reln, dict):
            relations.append({
                "relation_type": "update-to",
                "id": reln.get("DOI"),
                "id_type": "doi",
                "update_type": reln.get("type"),
                "locator": "%s.update-to[%d]" % (locator, j),
            })
    raw_status = {
        "type": item.get("type", NOT_PROVIDED),
        "subtype": item.get("subtype", NOT_PROVIDED),
        "relation_key_present": "relation" in item,
        "update_to_key_present": "update-to" in item,
    }
    return {
        "source_db": "crossref",
        "locator": locator,
        "doi_norm": norm_doi(item.get("DOI")),
        "pmid": None,
        "pmcid": None,
        "title": _first_str(item.get("title")),
        "year": _extract_year(item.get("issued")),
        "authors": authors,
        "pub_types": [item.get("type")] if item.get("type") else [],
        "relations": relations,
        "raw_status_fields": raw_status,
    }


def _norm_europepmc_item(item, rel, idx):
    locator = "%s::$.resultList.result[%d]" % (rel, idx)
    authors = []
    raw_authors = item.get("authorString")
    if isinstance(raw_authors, str):
        for name in [n.strip() for n in raw_authors.split(",") if n.strip()]:
            family = name.split(" ")[0] if name else None
            authors.append({"given": None, "family": family,
                            "surname_norm": norm_surname(family)})
    pub_types = []
    ptl = item.get("pubTypeList")
    if isinstance(ptl, dict) and isinstance(ptl.get("pubType"), list):
        pub_types = [p for p in ptl["pubType"] if isinstance(p, str)]
    raw_status = {
        "pubTypeList": pub_types if pub_types else NOT_PROVIDED,
        "source": item.get("source", NOT_PROVIDED),
        "pubTypeList_key_present": isinstance(ptl, dict),
    }
    return {
        "source_db": "europepmc",
        "locator": locator,
        "doi_norm": norm_doi(item.get("doi")),
        "pmid": str(item.get("id")) if item.get("id") is not None else None,
        "pmcid": item.get("pmcid"),
        "title": item.get("title") if isinstance(item.get("title"), str) else None,
        "year": _extract_year(str(item.get("pubYear", ""))),
        "authors": authors,
        "pub_types": pub_types,
        "relations": [],
        "raw_status_fields": raw_status,
    }


def _norm_publisher_item(item, rel, locator):
    authors = []
    for a in item.get("authors") or item.get("author") or []:
        if isinstance(a, dict):
            authors.append({"given": a.get("given"), "family": a.get("family"),
                            "surname_norm": norm_surname(a.get("family"))})
        elif isinstance(a, str):
            family = a.split(" ")[-1] if a.split(" ") else a
            authors.append({"given": None, "family": family,
                            "surname_norm": norm_surname(family)})
    raw_status = {
        "status": item.get("status", NOT_PROVIDED),
        "notice": item.get("notice", NOT_PROVIDED),
        "status_key_present": ("status" in item) or ("notice" in item),
    }
    return {
        "source_db": "publisher",
        "locator": locator,
        "doi_norm": norm_doi(item.get("doi") or item.get("DOI")),
        "pmid": str(item.get("pmid")) if item.get("pmid") else None,
        "pmcid": item.get("pmcid"),
        "title": item.get("title") if isinstance(item.get("title"), str) else None,
        "year": _extract_year(item.get("year") or item.get("issued")),
        "authors": authors,
        "pub_types": [],
        "relations": [],
        "raw_status_fields": raw_status,
    }


def assign_record_id(rec, seq):
    if rec.get("doi_norm"):
        rid = "%s:%s" % (rec["source_db"], rec["doi_norm"])
    elif rec.get("pmid"):
        rid = "%s:%s" % (rec["source_db"], rec["pmid"])
    else:
        seed = (rec.get("title_norm") or "") + "|" + rec["locator"]
        rid = "%s:anon:%s" % (rec["source_db"],
                              hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12])
    return rid


def cmd_parse(args):
    case, case_path = load_case(args.input)
    materials = discover_materials(case, args.input)
    os.makedirs(args.work, exist_ok=True)
    os.makedirs(args.output, exist_ok=True)

    records = []
    material_reports = []
    for mat in materials:
        report = {"rel": mat["rel"], "role": mat.get("role"),
                  "exists": mat["exists"], "sha256": None,
                  "sniffed_type": None, "records": 0}
        if not mat["exists"]:
            material_reports.append(report)
            continue
        raw = read_bytes(mat["path"])
        report["sha256"] = sha256_bytes(raw)
        text = raw.decode("utf-8-sig", errors="replace")
        parsed = None
        stype = None
        try:
            parsed = json.loads(text)
            stype = sniff_material(parsed)
        except Exception:  # noqa: BLE001
            stype = sniff_text_material(text)
        # role hint wins when sniffing is inconclusive
        if stype == "unknown" and mat.get("role") in (
                "crossref", "europepmc", "publisher", "reference_graph",
                "import_state"):
            stype = mat["role"]
        report["sniffed_type"] = stype

        new_records = []
        if stype == "crossref" and isinstance(parsed, dict):
            for i, item in enumerate(parsed["message"]["items"]):
                if isinstance(item, dict):
                    new_records.append(_norm_crossref_item(item, mat["rel"], i))
        elif stype == "europepmc" and isinstance(parsed, dict):
            for i, item in enumerate(parsed["resultList"]["result"]):
                if isinstance(item, dict):
                    new_records.append(_norm_europepmc_item(item, mat["rel"], i))
        elif stype == "publisher" and isinstance(parsed, list):
            for i, item in enumerate(parsed):
                if isinstance(item, dict):
                    new_records.append(_norm_publisher_item(
                        item, mat["rel"], "%s::$[%d]" % (mat["rel"], i)))
        elif stype == "publisher_jsonl":
            for i, ln in enumerate([l for l in text.splitlines() if l.strip()]):
                try:
                    item = json.loads(ln)
                except Exception:  # noqa: BLE001
                    continue
                if isinstance(item, dict):
                    new_records.append(_norm_publisher_item(
                        item, mat["rel"], "%s::$.line[%d]" % (mat["rel"], i)))
        elif stype == "publisher_csv":
            reader = csv.DictReader(text.splitlines())
            for i, row in enumerate(reader):
                new_records.append(_norm_publisher_item(
                    dict(row), mat["rel"], "%s::$.row[%d]" % (mat["rel"], i + 1)))
        # reference_graph / import_state / unknown: no literature records here;
        # they are consumed by scan / reconcile.
        for rec in new_records:
            rec["source_path"] = mat["rel"]
            rec["title_norm"] = norm_title(rec.get("title"))
            rec["jsonpath_locator"] = rec.pop("locator")
        report["records"] = len(new_records)
        records.extend(new_records)
        material_reports.append(report)

    # deterministic order, stable record ids
    records.sort(key=lambda r: (r["source_path"], r["jsonpath_locator"]))
    used_ids = {}
    for rec in records:
        base = assign_record_id(rec, len(used_ids))
        rid = base
        n = 2
        while rid in used_ids:
            rid = "%s#dup%d" % (base, n)
            n += 1
        used_ids[rid] = True
        rec["record_id"] = rid
        # field presence semantics: None means missing/unknown, NOT_PROVIDED
        # markers already embedded in raw_status_fields.

    task_path = os.path.join(args.input, "task.md")
    task_info = {"present": os.path.isfile(task_path), "sha256": None}
    if task_info["present"]:
        task_info["sha256"] = sha256_file(task_path)

    summary = {
        "case_id": case.get("case_id"),
        "skill_name": SKILL_NAME,
        "engine_version": VERSION,
        "research_question": case.get("research_question"),
        "source_dbs_declared": case.get("source_dbs") or [],
        "task_md": task_info,
        "materials": material_reports,
        "records_total": len(records),
        "output_contract_fields": sorted((case.get("output_contract") or {}).keys()),
        "missing_materials": [m["rel"] for m in material_reports
                              if not m["exists"]],
        "unknown_materials": [m["rel"] for m in material_reports
                              if m["exists"] and m["sniffed_type"] == "unknown"],
    }
    write_jsonl(os.path.join(args.work, "normalized.jsonl"), records)
    write_json(os.path.join(args.work, "case_summary.json"), summary)
    sys.stdout.write("parse: %d records from %d materials (%d missing, %d unknown)\n"
                     % (len(records), len(material_reports),
                        len(summary["missing_materials"]),
                        len(summary["unknown_materials"])))
    return 0


# --------------------------------------------------------------------------
# Signal extraction (scan)
# --------------------------------------------------------------------------
def _signal(record_id, code, locator, detail):
    return {
        "record_id": record_id,
        "code": code,
        "severity": REASON_SEVERITY.get(code, "info"),
        "evidence_locator": locator,
        "detail": detail,
    }


def _load_graph(case, args):
    """Load first reference_graph material. Returns dict or None."""
    for mat in discover_materials(case, args.input):
        if not mat["exists"]:
            continue
        if mat.get("role") == "reference_graph" or \
                mat["rel"].endswith("reference_graph.json"):
            try:
                data = json.loads(read_bytes(mat["path"]).decode("utf-8-sig"))
                if isinstance(data, dict):
                    data["_rel"] = mat["rel"]
                    return data
            except Exception:  # noqa: BLE001
                continue
    return None


def cmd_scan(args):
    norm_path = os.path.join(args.work, "normalized.jsonl")
    if not os.path.isfile(norm_path):
        sys.stderr.write(
            "scan: %s missing — run `parse` first (no materials normalized)\n"
            % norm_path)
        return 2
    records = read_jsonl(norm_path)
    if not records:
        sys.stderr.write(
            "scan: 0 normalized records — no materials to scan; "
            "refusing to fabricate a clean bill of health\n")
        return 2
    case, _ = load_case(args.input)

    by_doi = {}
    for rec in records:
        if rec.get("doi_norm"):
            by_doi.setdefault(rec["doi_norm"], rec)

    signals = []

    # ---- per-record native signals -------------------------------------
    for rec in records:
        rid = rec["record_id"]
        loc = rec["jsonpath_locator"]
        src = rec["source_db"]
        raw = rec.get("raw_status_fields") or {}

        if src == "crossref":
            ctype = raw.get("type")
            subtype = raw.get("subtype")
            if ctype == "posted-content" or subtype == "preprint":
                signals.append(_signal(
                    rid, "CROSSREF_POSTED_CONTENT", loc,
                    "type=%r subtype=%r => preprint marker" % (ctype, subtype)))
            for j, reln in enumerate(rec.get("relations") or []):
                rtype = (reln.get("relation_type") or "").lower()
                rloc = reln.get("locator") or ("%s.relation[%d]" % (loc, j))
                target = norm_doi(reln.get("id")) or reln.get("id")
                if rtype in NOTICE_RELATIONS_SEVERE:
                    signals.append(_signal(
                        rid, "CROSSREF_IS_RETRACTION_OF", rloc,
                        "this record IS a retraction notice for %s" % target))
                    tgt = by_doi.get(target)
                    if tgt:
                        signals.append(_signal(
                            tgt["record_id"], "TARGET_RETRACTED", rloc,
                            "retracted by notice %s (doi %s)"
                            % (rid, rec.get("doi_norm"))))
                elif rtype in NOTICE_RELATIONS_FLAGGED:
                    code = ("CROSSREF_IS_ERRATUM_OF"
                            if "erratum" in rtype or "correction" in rtype
                            else "CROSSREF_IS_EXPRESSION_OF_CONCERN_OF")
                    signals.append(_signal(
                        rid, code, rloc,
                        "this record IS a %s notice for %s" % (rtype, target)))
                    tgt = by_doi.get(target)
                    if tgt:
                        tcode = ("TARGET_CORRECTED" if "erratum" in rtype or
                                 "correction" in rtype else "TARGET_CONCERNED")
                        signals.append(_signal(
                            tgt["record_id"], tcode, rloc,
                            "target of %s notice %s" % (rtype, rid)))
                elif rtype in AFFECTED_RELATIONS_SEVERE:
                    signals.append(_signal(
                        rid, "CROSSREF_HAS_RETRACTION", rloc,
                        "this record has been retracted (notice %s)" % target))
                elif rtype in AFFECTED_RELATIONS_FLAGGED:
                    code = ("CROSSREF_HAS_ERRATUM" if "erratum" in rtype or
                            "correction" in rtype
                            else "CROSSREF_HAS_EXPRESSION_OF_CONCERN")
                    signals.append(_signal(
                        rid, code, rloc,
                        "this record has a %s notice (%s)" % (rtype, target)))
                elif rtype in UPDATE_RELATIONS:
                    signals.append(_signal(
                        rid, UPDATE_RELATIONS[rtype], rloc,
                        "Crossref %s relation to %s (update type %s)"
                        % (rtype, target, reln.get("update_type", "unknown"))))
                elif rtype in PREPRINT_RELATIONS:
                    signals.append(_signal(
                        rid, "CROSSREF_PREPRINT_RELATION", rloc,
                        "%s -> %s" % (rtype, target)))

        elif src == "europepmc":
            pts = [p.lower() for p in (rec.get("pub_types") or [])]
            for pt in pts:
                if pt in EPMC_SEVERE_PUBTYPES:
                    signals.append(_signal(
                        rid, EPMC_SEVERE_PUBTYPES[pt],
                        loc + ".pubTypeList",
                        "pubTypeList contains %r" % pt))
                elif pt in EPMC_FLAGGED_PUBTYPES:
                    signals.append(_signal(
                        rid, EPMC_FLAGGED_PUBTYPES[pt],
                        loc + ".pubTypeList",
                        "pubTypeList contains %r" % pt))
                elif pt == "preprint":
                    signals.append(_signal(
                        rid, "EPMC_PREPRINT", loc + ".pubTypeList",
                        "pubTypeList contains 'preprint'"))
            if str(raw.get("source", "")).upper() == "PPR" and \
                    not any(s["record_id"] == rid and s["code"] == "EPMC_PREPRINT"
                            for s in signals):
                signals.append(_signal(
                    rid, "EPMC_PREPRINT", loc + ".source",
                    "EuropePMC source=PPR (preprint server)"))

        elif src == "publisher":
            status = raw.get("status")
            if isinstance(status, str):
                st = status.strip().lower()
                if st in PUBLISHER_STATUS_SEVERE:
                    signals.append(_signal(
                        rid, "PUBLISHER_STATUS_RETRACTED", loc + ".status",
                        "publisher status=%r" % status))
                elif st in PUBLISHER_STATUS_FLAGGED:
                    signals.append(_signal(
                        rid, "PUBLISHER_STATUS_NOTICE", loc + ".status",
                        "publisher status=%r" % status))

    # ---- reference graph signals ---------------------------------------
    graph = _load_graph(case, args)
    if graph:
        grel = graph.get("_rel", "reference_graph.json")
        nodes = graph.get("nodes") or []
        edges = graph.get("edges") or []
        for i, node in enumerate(nodes):
            if not isinstance(node, dict):
                continue
            nid = norm_doi(node.get("id")) or node.get("id")
            status = node.get("status")
            withdrawn = node.get("withdrawn")
            rec = by_doi.get(nid)
            if not rec:
                continue
            nloc = "%s::$.nodes[%d]" % (grel, i)
            st = str(status).strip().lower() if status is not None else None
            if withdrawn is True or (st in GRAPH_NODE_SEVERE):
                signals.append(_signal(
                    rec["record_id"], "REFGRAPH_NODE_WITHDRAWN", nloc,
                    "reference graph node status=%r withdrawn=%r"
                    % (status, withdrawn)))
            elif st in GRAPH_NODE_FLAGGED:
                signals.append(_signal(
                    rec["record_id"], "REFGRAPH_NODE_NOTICE", nloc,
                    "reference graph node status=%r" % status))
        for i, edge in enumerate(edges):
            if not isinstance(edge, dict):
                continue
            etype = str(edge.get("type") or "").strip().lower()
            if etype not in GRAPH_EDGE_RETRACTION:
                continue
            tgt = by_doi.get(norm_doi(edge.get("to")) or edge.get("to"))
            if tgt:
                signals.append(_signal(
                    tgt["record_id"], "REFGRAPH_RETRACTION_EDGE",
                    "%s::$.edges[%d]" % (grel, i),
                    "graph edge type=%r from %s" % (etype, edge.get("from"))))

    # ---- cross-source status conflicts ---------------------------------
    for rec in records:
        rid = rec["record_id"]
        rec_sigs = [s for s in signals if s["record_id"] == rid]
        severe_here = any(s["severity"] == "severe" for s in rec_sigs)
        if not severe_here:
            continue
        raw = rec.get("raw_status_fields") or {}
        pub_status = raw.get("status")
        if isinstance(pub_status, str) and \
                pub_status.strip().lower() in ("published", "active", "live"):
            signals.append(_signal(
                rid, "STATUS_SOURCE_CONFLICT", rec["jsonpath_locator"],
                "publisher declares status=%r but another source marks this "
                "record retracted/withdrawn" % pub_status))

    signals.sort(key=lambda s: (s["record_id"], s["code"],
                                s["evidence_locator"]))
    write_jsonl(os.path.join(args.work, "status_signals.jsonl"), signals)
    sys.stdout.write("scan: %d signals over %d records "
                     "(severe=%d flagged=%d info=%d)\n"
                     % (len(signals), len(records),
                        sum(1 for s in signals if s["severity"] == "severe"),
                        sum(1 for s in signals if s["severity"] == "flagged"),
                        sum(1 for s in signals if s["severity"] == "info")))
    return 0


# --------------------------------------------------------------------------
# Preprint <-> VoR pairing (pair)
# --------------------------------------------------------------------------
def _is_preprint(rec, sigs):
    for s in sigs:
        if s["record_id"] == rec["record_id"] and s["code"] in (
                "CROSSREF_POSTED_CONTENT", "EPMC_PREPRINT"):
            return True
    return False


def cmd_pair(args):
    records = read_jsonl(os.path.join(args.work, "normalized.jsonl"))
    sig_path = os.path.join(args.work, "status_signals.jsonl")
    signals = read_jsonl(sig_path) if os.path.isfile(sig_path) else []
    by_doi = {r["doi_norm"]: r for r in records if r.get("doi_norm")}
    by_id = {r["record_id"]: r for r in records}

    pairs = []
    pending = []
    seen_pair_keys = set()

    def add_pair(pre, vor, basis, evidence, status):
        key = (pre["record_id"] if pre else None,
               vor["record_id"] if vor else None)
        if key in seen_pair_keys:
            return
        seen_pair_keys.add(key)
        pairs.append({
            "pair_id": "pair-%02d" % (len(pairs) + 1),
            "preprint_record_id": pre["record_id"] if pre else None,
            "preprint_doi": pre.get("doi_norm") if pre else None,
            "vor_record_id": vor["record_id"] if vor else None,
            "vor_doi": vor.get("doi_norm") if vor else None,
            "basis": basis,
            "status": status,
            "evidence": evidence,
        })

    # 1) explicit relation links
    for rec in records:
        for reln in rec.get("relations") or []:
            rtype = (reln.get("relation_type") or "").lower()
            if rtype not in PREPRINT_RELATIONS:
                continue
            target = by_doi.get(norm_doi(reln.get("id")))
            if rtype == "is-preprint-of":
                pre, vor = rec, target
            else:  # has-preprint
                vor, pre = rec, target
            evidence = [reln.get("locator")]
            if target is None:
                # explicit link but counterpart absent from materials
                pending.append({
                    "preprint_record_id": pre["record_id"],
                    "claimed_counterpart_doi": norm_doi(reln.get("id")),
                    "basis": "explicit_external",
                    "reason": "explicit %s relation points to a DOI absent "
                              "from all present materials; cannot fold" % rtype,
                    "evidence": evidence,
                })
                continue
            add_pair(pre, vor, "explicit", evidence, "explicit_resolved")

    # 2) bibliographic fallback -> review queue ONLY (never auto-pair)
    preprints = [r for r in records if _is_preprint(r, signals)]
    vors = [r for r in records if not _is_preprint(r, signals)]
    paired_pre_ids = {p["preprint_record_id"] for p in pairs}
    paired_vor_ids = {p["vor_record_id"] for p in pairs}
    for pre in preprints:
        if pre["record_id"] in paired_pre_ids or not pre.get("title_norm"):
            continue
        for vor in vors:
            if vor["record_id"] in paired_vor_ids:
                continue
            if not vor.get("title_norm") or \
                    vor["title_norm"] != pre["title_norm"]:
                continue
            pre_au = (pre.get("authors") or [{}])
            vor_au = (vor.get("authors") or [{}])
            pre_sur = pre_au[0].get("surname_norm") if pre_au else None
            vor_sur = vor_au[0].get("surname_norm") if vor_au else None
            if not pre_sur or pre_sur != vor_sur:
                continue
            py, vy = pre.get("year"), vor.get("year")
            if isinstance(py, int) and isinstance(vy, int) and abs(py - vy) > 1:
                continue
            pending.append({
                "preprint_record_id": pre["record_id"],
                "candidate_vor_record_id": vor["record_id"],
                "basis": "ambiguous",
                "reason": "bibliographic fallback (title+first-author+year±1) "
                          "match — REQUIRES model adjudication, not auto-paired",
                "evidence": [pre["jsonpath_locator"], vor["jsonpath_locator"]],
            })

    out = {
        "pairs": pairs,
        "pending_review": pending,
        "rule": "When a pair is confirmed, the candidate set counts ONE study "
                "with both identifiers; the VoR is preferred for citation "
                "fields; the preprint is kept as alternate_version. Explicit "
                "relation links auto-pair; bibliographic fallback NEVER "
                "auto-pairs — it waits in pending_review for a "
                "merge_version_pair / split_not_same disposition.",
        "counts": {"pairs_explicit": len(pairs),
                   "pairs_pending": len(pending)},
    }
    write_json(os.path.join(args.work, "version_pairs.json"), out)
    sys.stdout.write("pair: %d explicit pairs, %d pending review\n"
                     % (len(pairs), len(pending)))
    return 0


# --------------------------------------------------------------------------
# import_state reconciliation (reconcile)
# --------------------------------------------------------------------------
def _load_import_state(case, args):
    for mat in discover_materials(case, args.input):
        if not mat["exists"]:
            continue
        if mat.get("role") == "import_state" or \
                mat["rel"].endswith("import_state.json"):
            try:
                data = json.loads(read_bytes(mat["path"]).decode("utf-8-sig"))
                if isinstance(data, dict):
                    data["_rel"] = mat["rel"]
                    return data
            except Exception:  # noqa: BLE001
                continue
    return None


def cmd_reconcile(args):
    records = read_jsonl(os.path.join(args.work, "normalized.jsonl"))
    case, _ = load_case(args.input)
    state = _load_import_state(case, args)

    by_doi = {}
    by_pmid = {}
    for r in records:
        if r.get("doi_norm"):
            by_doi.setdefault(r["doi_norm"], r)
        if r.get("pmid"):
            by_pmid.setdefault(r["pmid"], r)

    entries = []
    if state is None:
        result = {
            "import_state_present": False,
            "entries": [],
            "import_inconsistent": [],
            "withdrawn_excluded": [],
            "not_yet_imported": [],
            "note": "no import_state material in this case; reconciliation "
                    "vacuous — absence is declared, not treated as clean",
        }
        write_json(os.path.join(args.work, "reconcile.json"), result)
        sys.stdout.write("reconcile: no import_state present (declared)\n")
        return 0

    raw_entries = state.get("records") or state.get("entries") or []
    srel = state.get("_rel", "import_state.json")
    for i, entry in enumerate(raw_entries):
        if not isinstance(entry, dict):
            continue
        db = entry.get("db")
        ident = entry.get("identifier")
        st = str(entry.get("status") or "").strip().lower()
        eloc = "%s::$.records[%d]" % (srel, i)
        rec = None
        if looks_like_doi(ident):
            rec = by_doi.get(norm_doi(ident))
        if rec is None and ident is not None:
            rec = by_pmid.get(str(ident))
        if rec is None and looks_like_doi(ident) is False:
            rec = by_doi.get(norm_doi(ident))
        verdict = None
        if st in IMPORT_WITHDRAWN_STATES:
            verdict = ("withdrawn_excluded" if rec else "withdrawn_absent")
        elif rec is None:
            verdict = "import_inconsistent"
        else:
            verdict = "consistent"
        entries.append({
            "db": db,
            "identifier": ident,
            "status": entry.get("status"),
            "verdict": verdict,
            "matched_record_id": rec["record_id"] if rec else None,
            "evidence_locator": eloc,
        })

    claimed_ids = {e["matched_record_id"] for e in entries
                   if e["matched_record_id"]}
    not_yet = sorted(r["record_id"] for r in records
                     if r["record_id"] not in claimed_ids)
    result = {
        "import_state_present": True,
        "entries": entries,
        "import_inconsistent": [e for e in entries
                                if e["verdict"] == "import_inconsistent"],
        "withdrawn_excluded": [e for e in entries
                               if e["verdict"] == "withdrawn_excluded"],
        "not_yet_imported": not_yet,
        "note": "import_inconsistent entries are quarantined (claimed imported "
                "but absent from every present response); withdrawn entries "
                "must be excluded from the candidate pool with reason; "
                "not_yet_imported is informational only.",
    }
    write_json(os.path.join(args.work, "reconcile.json"), result)
    sys.stdout.write("reconcile: %d entries (%d inconsistent, %d withdrawn, "
                     "%d not-yet-imported records)\n"
                     % (len(entries), len(result["import_inconsistent"]),
                        len(result["withdrawn_excluded"]), len(not_yet)))
    return 0


# --------------------------------------------------------------------------
# Model adjudication (adjudicate)
# --------------------------------------------------------------------------
def cmd_adjudicate(args):
    disp_path = args.dispositions
    if not disp_path or not os.path.isfile(disp_path):
        sys.stderr.write("adjudicate: dispositions file missing: %s\n"
                         % disp_path)
        return 2
    try:
        payload = json.loads(read_bytes(disp_path).decode("utf-8-sig"))
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write("adjudicate: dispositions not valid JSON: %s\n" % exc)
        return 2
    items = payload.get("dispositions") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        sys.stderr.write("adjudicate: expected {\"dispositions\": [...]}\n")
        return 2

    records = read_jsonl(os.path.join(args.work, "normalized.jsonl"))
    by_id = {r["record_id"]: r for r in records}
    pairs_path = os.path.join(args.work, "version_pairs.json")
    pair_data = {}
    if os.path.isfile(pairs_path):
        pair_data = json.loads(read_bytes(pairs_path).decode("utf-8"))
    pending = pair_data.get("pending_review") or []
    confirmed_pairs = pair_data.get("pairs") or []

    applied, rejected = [], []
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            rejected.append({"index": i, "reason": "not an object"})
            continue
        disp = item.get("disposition")
        rid = item.get("record_id")
        rationale = item.get("rationale")
        problems = []
        if disp not in ALLOWED_DISPOSITIONS:
            problems.append("disposition must be one of %s"
                            % sorted(ALLOWED_DISPOSITIONS))
        if not isinstance(rationale, str) or len(rationale.strip()) < 10:
            problems.append("rationale missing or shorter than 10 characters")
        if disp in ("merge_version_pair", "split_not_same"):
            target_pre = item.get("preprint_record_id") or rid
            known = any(p.get("preprint_record_id") == target_pre
                        for p in pending) or \
                any(p.get("preprint_record_id") == target_pre
                    for p in confirmed_pairs)
            if not known:
                problems.append("no known pair/pending entry for "
                                "preprint_record_id=%r" % target_pre)
        else:
            if rid not in by_id:
                problems.append("unknown record_id %r" % rid)
        if problems:
            rejected.append({"index": i, "record_id": rid,
                             "disposition": disp, "reasons": problems})
        else:
            applied.append({
                "record_id": rid,
                "preprint_record_id": item.get("preprint_record_id"),
                "disposition": disp,
                "rationale": rationale.strip(),
            })
    out = {"applied": applied, "rejected": rejected,
           "source_file": os.path.basename(disp_path)}
    write_json(os.path.join(args.work, "dispositions_applied.json"), out)
    sys.stdout.write("adjudicate: %d applied, %d rejected\n"
                     % (len(applied), len(rejected)))
    return 2 if rejected else 0


# --------------------------------------------------------------------------
# Finalization (finalize)
# --------------------------------------------------------------------------
def _status_surface(rec, graph, sigs):
    """Does this record expose ANY surface on which status could have been
    declared? If not, 'no bad news found' must NOT be read as 'clean'."""
    raw = rec.get("raw_status_fields") or {}
    if rec["source_db"] == "crossref" and \
            (raw.get("relation_key_present") or raw.get("update_to_key_present")):
        return True
    if rec["source_db"] == "europepmc" and raw.get("pubTypeList_key_present"):
        return True
    if rec["source_db"] == "publisher" and raw.get("status_key_present"):
        return True
    if any(s["record_id"] == rec["record_id"] and
           s["code"].startswith("REFGRAPH") for s in sigs):
        return True
    if graph and rec.get("doi_norm"):
        for node in graph.get("nodes") or []:
            if isinstance(node, dict) and \
                    (norm_doi(node.get("id")) == rec["doi_norm"]):
                return True
    return False


def cmd_finalize(args):
    work = args.work
    records = read_jsonl(os.path.join(work, "normalized.jsonl"))
    summary = json.loads(read_bytes(os.path.join(work, "case_summary.json"))
                         .decode("utf-8"))
    sig_path = os.path.join(work, "status_signals.jsonl")
    signals = read_jsonl(sig_path) if os.path.isfile(sig_path) else []
    pairs_path = os.path.join(work, "version_pairs.json")
    pair_data = json.loads(read_bytes(pairs_path).decode("utf-8")) \
        if os.path.isfile(pairs_path) else {"pairs": [], "pending_review": []}
    rec_path = os.path.join(work, "reconcile.json")
    reconcile = json.loads(read_bytes(rec_path).decode("utf-8")) \
        if os.path.isfile(rec_path) else {"import_state_present": False,
                                          "entries": [],
                                          "import_inconsistent": [],
                                          "withdrawn_excluded": [],
                                          "not_yet_imported": []}
    disp_path = os.path.join(work, "dispositions_applied.json")
    dispositions = json.loads(read_bytes(disp_path).decode("utf-8")) \
        if os.path.isfile(disp_path) else {"applied": [], "rejected": []}
    case, _ = load_case(args.input)
    graph = _load_graph(case, args)

    # import-withdrawn records get a synthetic severe signal
    for w in reconcile.get("withdrawn_excluded") or []:
        rid = w.get("matched_record_id")
        if rid:
            signals.append(_signal(
                rid, "IMPORT_STATE_WITHDRAWN", w["evidence_locator"],
                "import_state marks db=%r identifier=%r as %r — excluded "
                "from candidate pool" % (w.get("db"), w.get("identifier"),
                                         w.get("status"))))
    for e in reconcile.get("not_yet_imported") or []:
        signals.append(_signal(
            e, "IMPORT_NOT_YET_IMPORTED", None,
            "record present in responses but unknown to import_state "
            "(informational)"))
    signals.sort(key=lambda s: (s["record_id"], s["code"],
                                s["evidence_locator"] or ""))

    disp_by_record = {}
    for d in dispositions.get("applied") or []:
        if d.get("record_id"):
            disp_by_record[d["record_id"]] = d
    merge_decisions = {d.get("preprint_record_id") or d.get("record_id"): d
                       for d in (dispositions.get("applied") or [])
                       if d["disposition"] == "merge_version_pair"}

    # ---- per-record ledger ---------------------------------------------
    pair_of = {}
    for p in pair_data.get("pairs") or []:
        if p.get("preprint_record_id"):
            pair_of[p["preprint_record_id"]] = {"pair_id": p["pair_id"],
                                                "role": "preprint"}
        if p.get("vor_record_id"):
            pair_of[p["vor_record_id"]] = {"pair_id": p["pair_id"],
                                           "role": "vor"}
    for pend in pair_data.get("pending_review") or []:
        pre_id = pend.get("preprint_record_id")
        if pre_id and pre_id in merge_decisions:
            vor_id = pend.get("candidate_vor_record_id")
            pid = "pair-review-%02d" % (len(pair_of) + 1)
            pair_of[pre_id] = {"pair_id": pid, "role": "preprint"}
            if vor_id:
                pair_of[vor_id] = {"pair_id": pid, "role": "vor"}
            pair_data.setdefault("pairs", []).append({
                "pair_id": pid, "preprint_record_id": pre_id,
                "preprint_doi": None, "vor_record_id": vor_id, "vor_doi": None,
                "basis": "ambiguous_confirmed_by_model", "status": "merged",
                "evidence": pend.get("evidence") or [],
            })

    ledger = []
    for rec in records:
        rid = rec["record_id"]
        rec_sigs = [s for s in signals if s["record_id"] == rid]
        sev_set = {s["severity"] for s in rec_sigs}
        if "severe" in sev_set:
            status_class = "severe"
        elif "flagged" in sev_set:
            status_class = "flagged"
        elif _status_surface(rec, graph, signals):
            status_class = "clean"
        else:
            status_class = "unverifiable"
        d = disp_by_record.get(rid)
        if d:
            final_disp = d["disposition"]
            disp_note = d["rationale"]
        elif status_class == "severe":
            final_disp = "exclude_as_retracted"
            disp_note = "policy default for severe status signals " \
                        "(model may override with rationale)"
        elif status_class == "clean":
            final_disp = "keep_clean"
            disp_note = "no adverse signal on any status surface"
        elif status_class == "unverifiable":
            final_disp = "status_unverifiable"
            disp_note = "no status-bearing surface in materials; absence of " \
                        "evidence is NOT evidence of clean status"
        else:
            final_disp = "pending_model_review"
            disp_note = "flagged record awaiting model adjudication"
        ledger.append({
            "record_id": rid,
            "source_db": rec["source_db"],
            "source_path": rec["source_path"],
            "jsonpath_locator": rec["jsonpath_locator"],
            "doi_norm": rec.get("doi_norm"),
            "pmid": rec.get("pmid"),
            "title": rec.get("title"),
            "year": rec.get("year"),
            "status_class": status_class,
            "signals": rec_sigs,
            "pair_membership": pair_of.get(rid),
            "final_disposition": final_disp,
            "disposition_note": disp_note,
        })
    ledger.sort(key=lambda e: e["record_id"])

    # ---- candidate pool with version-pair folding -----------------------
    folded_preprints = {}
    for p in pair_data.get("pairs") or []:
        if p.get("preprint_record_id") and p.get("vor_record_id"):
            folded_preprints[p["preprint_record_id"]] = p["vor_record_id"]
    candidates, excluded, unverifiable_list = [], [], []
    ledger_by_id = {e["record_id"]: e for e in ledger}
    rec_by_id = {r["record_id"]: r for r in records}
    for entry in ledger:
        rid = entry["record_id"]
        if rid in folded_preprints:
            continue  # folded into the VoR candidate below
        if entry["status_class"] == "severe":
            excluded.append({
                "record_id": rid,
                "reason_codes": sorted({s["code"] for s in entry["signals"]
                                        if s["severity"] == "severe"}),
                "disposition": entry["final_disposition"],
            })
            continue
        if entry["status_class"] == "unverifiable":
            unverifiable_list.append(rid)
            continue
        if entry["final_disposition"] in ("exclude_as_retracted",):
            excluded.append({"record_id": rid,
                             "reason_codes": ["MODEL_EXCLUDED"],
                             "disposition": entry["final_disposition"]})
            continue
        rec = rec_by_id[rid]
        alt = None
        membership = entry.get("pair_membership")
        if membership and membership["role"] == "vor":
            for p in pair_data.get("pairs") or []:
                if p.get("pair_id") == membership["pair_id"] and \
                        p.get("preprint_record_id"):
                    pre_rec = rec_by_id.get(p["preprint_record_id"])
                    if pre_rec:
                        alt = {"record_id": pre_rec["record_id"],
                               "doi": pre_rec.get("doi_norm"),
                               "source_db": pre_rec["source_db"],
                               "version_role": "preprint"}
        candidates.append({
            "candidate_id": "cand-%02d" % (len(candidates) + 1),
            "primary_record_id": rid,
            "doi": rec.get("doi_norm"),
            "pmid": rec.get("pmid"),
            "title": rec.get("title"),
            "year": rec.get("year"),
            "authors": [a.get("family") for a in (rec.get("authors") or [])
                        if a.get("family")],
            "source_db": rec["source_db"],
            "status_class": entry["status_class"],
            "notice": [s["code"] for s in entry["signals"]
                       if s["severity"] == "flagged"] or None,
            "version_role": "version_of_record" if alt else "single",
            "alternate_version": alt,
            "counts_as_studies": 1,
        })

    candidate_pool = {
        "rule": pair_data.get("rule"),
        "candidates": candidates,
        "excluded": excluded,
        "unverifiable_not_included": unverifiable_list,
        "folded_preprints": folded_preprints,
        "studies_count": len(candidates),
    }

    # ---- ledger & report & result ---------------------------------------
    counts = {
        "records_scanned": len(ledger),
        "severe": sum(1 for e in ledger if e["status_class"] == "severe"),
        "flagged": sum(1 for e in ledger if e["status_class"] == "flagged"),
        "unverifiable": sum(1 for e in ledger
                            if e["status_class"] == "unverifiable"),
        "pairs_explicit": len([p for p in pair_data.get("pairs") or []
                               if p.get("basis") == "explicit"]),
        "pairs_pending": len([p for p in pair_data.get("pending_review") or []
                              if (p.get("preprint_record_id") or "") not in
                              merge_decisions]),
        "import_inconsistent": len(reconcile.get("import_inconsistent") or []),
    }

    os.makedirs(args.output, exist_ok=True)
    write_json(os.path.join(args.output, "status_ledger.json"),
               {"case_id": summary.get("case_id"), "skill_name": SKILL_NAME,
                "records": ledger, "counts": counts})
    write_json(os.path.join(args.output, "candidate_pool.json"), candidate_pool)
    write_json(os.path.join(args.output, "version_pairs.json"), pair_data)

    # human-readable report
    lines = []
    lines.append("# 文献状态卫生报告（Record Status Hygiene Report）")
    lines.append("")
    lines.append("- case_id: `%s`" % summary.get("case_id"))
    lines.append("- skill: `%s` v%s" % (SKILL_NAME, VERSION))
    lines.append("- 记录总数: %(records_scanned)d | severe: %(severe)d | "
                 "flagged: %(flagged)d | unverifiable: %(unverifiable)d | "
                 "显式版本对: %(pairs_explicit)d | 待审版本对: "
                 "%(pairs_pending)d | import 不一致: %(import_inconsistent)d"
                 % counts)
    lines.append("")
    lines.append("> 本报告全部状态证据来自案例材料内部的显式字段/关系/引用图"
                 "属性；未做任何外部撤回库查询。查不到状态 ≠ 干净：无状态面"
                 "的记录一律标 `unverifiable`，不进入候选池。")
    lines.append("")

    def _table(title, rows, headers, rowfn):
        lines.append("## %s" % title)
        lines.append("")
        if not rows:
            lines.append("（无）")
        else:
            lines.append("| " + " | ".join(headers) + " |")
            lines.append("|" + "---|" * len(headers))
            for r in rows:
                lines.append("| " + " | ".join(rowfn(r)) + " |")
        lines.append("")

    severe_rows = [e for e in ledger if e["status_class"] == "severe"]
    _table("严重状态记录（severe — 一律排除出候选池）", severe_rows,
           ["record_id", "doi", "原因码", "证据定位符", "处置"],
           lambda e: [e["record_id"], str(e["doi_norm"]),
                      ", ".join(sorted({s["code"] for s in e["signals"]
                                        if s["severity"] == "severe"})),
                      "; ".join(s["evidence_locator"] for s in e["signals"]
                                if s["severity"] == "severe"
                                and s["evidence_locator"]),
                      e["final_disposition"]])
    flagged_rows = [e for e in ledger if e["status_class"] == "flagged"]
    _table("标记记录（flagged — 需模型裁定）", flagged_rows,
           ["record_id", "doi", "原因码", "证据定位符", "处置"],
           lambda e: [e["record_id"], str(e["doi_norm"]),
                      ", ".join(sorted({s["code"] for s in e["signals"]
                                        if s["severity"] == "flagged"})),
                      "; ".join(s["evidence_locator"] for s in e["signals"]
                                if s["severity"] == "flagged"
                                and s["evidence_locator"]),
                      e["final_disposition"]])
    _table("状态不可核验记录（unverifiable — 不视为干净，不入候选池）",
           unverifiable_list, ["record_id"],
           lambda rid: [rid])

    lines.append("## 版本归并（preprint ↔ VoR）")
    lines.append("")
    if pair_data.get("pairs"):
        lines.append("| pair_id | preprint | VoR | 依据 | 证据 |")
        lines.append("|---|---|---|---|---|")
        for p in pair_data["pairs"]:
            lines.append("| %s | %s | %s | %s | %s |"
                         % (p.get("pair_id"), p.get("preprint_record_id"),
                            p.get("vor_record_id"), p.get("basis"),
                            "; ".join(p.get("evidence") or [])))
    else:
        lines.append("（无已确认版本对）")
    lines.append("")
    pending_left = [p for p in (pair_data.get("pending_review") or [])
                    if (p.get("preprint_record_id") or "") not in
                    merge_decisions]
    if pending_left:
        lines.append("### 待人工/模型审核的候选版本对（未自动归并）")
        lines.append("")
        for p in pending_left:
            lines.append("- `%s` ⇄ `%s`（%s）"
                         % (p.get("preprint_record_id"),
                            p.get("candidate_vor_record_id") or
                            p.get("claimed_counterpart_doi"), p.get("reason")))
        lines.append("")

    lines.append("## import_state 对账")
    lines.append("")
    if reconcile.get("import_state_present"):
        for e in reconcile.get("import_inconsistent") or []:
            lines.append("- **import_inconsistent**: `%s` / `%s` — 声称已导入"
                         "但在所有在场响应中均不存在（隔离该声明；证据 `%s`）"
                         % (e.get("db"), e.get("identifier"),
                            e.get("evidence_locator")))
        for e in reconcile.get("withdrawn_excluded") or []:
            lines.append("- **withdrawn_excluded**: `%s` / `%s` — import_state "
                         "标记 %r，已从候选池排除（证据 `%s`）"
                         % (e.get("db"), e.get("identifier"), e.get("status"),
                            e.get("evidence_locator")))
        lines.append("- not_yet_imported（信息性）: %s"
                     % (", ".join("`%s`" % r for r in
                                  reconcile.get("not_yet_imported") or [])
                        or "无"))
    else:
        lines.append("案例中无 import_state 材料；对账为空操作（已声明，"
                     "不视为干净）。")
    lines.append("")
    lines.append("## 候选池结论")
    lines.append("")
    lines.append("- 入选候选（状态核验通过或保留并附注意）: **%d 项研究**"
                 % len(candidates))
    lines.append("- 排除（severe / 模型排除）: %d 条记录"
                 % len(excluded))
    lines.append("- 状态不可核验（未入选，需人工补证）: %d 条记录"
                 % len(unverifiable_list))
    lines.append("")
    write_text(os.path.join(args.output, "status_report.md"),
               "\n".join(lines))

    # ---- result.json -----------------------------------------------------
    contract = case.get("output_contract") or {}
    severe_ids = [e["record_id"] for e in severe_rows]
    contract_values = {}
    unresolved = []
    for field in sorted(contract.keys()):
        if field == "status_ledger":
            contract_values[field] = "status_ledger.json"
        elif field == "candidate_pool":
            contract_values[field] = "candidate_pool.json"
        elif field == "retraction_exclusions":
            contract_values[field] = [
                {"record_id": e["record_id"],
                 "reason_codes": sorted({s["code"] for s in e["signals"]
                                         if s["severity"] == "severe"})}
                for e in severe_rows]
        elif field == "version_pairs":
            contract_values[field] = "version_pairs.json"
        elif field == "import_reconciliation":
            contract_values[field] = {
                "import_state_present": reconcile.get("import_state_present"),
                "import_inconsistent": reconcile.get("import_inconsistent"),
                "withdrawn_excluded": reconcile.get("withdrawn_excluded"),
                "not_yet_imported": reconcile.get("not_yet_imported"),
            }
        elif field == "status_summary":
            contract_values[field] = counts
        else:
            contract_values[field] = None
            unresolved.append(field)

    pending_review_left = [p.get("preprint_record_id")
                           for p in pending_left]
    uncertainty = []
    if counts["unverifiable"]:
        uncertainty.append(
            {"kind": "status_unverifiable",
             "records": unverifiable_list,
             "statement": "这些记录在材料内没有任何状态承载面（无 relation/"
                          "pubTypeList/status/图节点）；查不到状态≠干净，"
                          "未入候选池，需人工补证后才能采信。"})
    if pending_review_left:
        uncertainty.append(
            {"kind": "pending_version_pairs",
             "records": pending_review_left,
             "statement": "书目学回退匹配的疑似 preprint↔VoR 对，未获模型 "
                          "merge_version_pair 裁定，未折叠，各自独立计数。"})
    if reconcile.get("import_inconsistent"):
        uncertainty.append(
            {"kind": "import_inconsistent",
             "records": [e.get("identifier")
                         for e in reconcile["import_inconsistent"]],
             "statement": "import_state 声称已导入但所有在场响应中均不存在"
                          "的标识符；该声明已被隔离，未影响候选池。"})
    if not reconcile.get("import_state_present"):
        uncertainty.append(
            {"kind": "import_state_absent",
             "statement": "无 import_state 材料，撤回式导入治理不可执行。"})
    if summary.get("missing_materials"):
        uncertainty.append(
            {"kind": "missing_materials",
             "records": summary["missing_materials"],
             "statement": "case.json 引用但磁盘缺失的材料。"})
    if not summary.get("task_md", {}).get("present"):
        uncertainty.append({"kind": "task_md_missing",
                            "statement": "task.md 缺失。"})

    change_records = []
    for e in severe_rows:
        change_records.append(
            {"action": "exclude_from_candidate_pool",
             "record_id": e["record_id"],
             "reason": sorted({s["code"] for s in e["signals"]
                               if s["severity"] == "severe"})})
    for rid, vor in folded_preprints.items():
        change_records.append(
            {"action": "fold_version_pair",
             "record_id": rid, "into": vor,
             "reason": "preprint↔VoR 归并：候选集按一项研究计数，VoR 优先"})
    for rid in unverifiable_list:
        change_records.append(
            {"action": "withhold_unverifiable",
             "record_id": rid,
             "reason": "无状态承载面，标 status_unverifiable 而非 clean"})

    sources = []
    for m in summary.get("materials") or []:
        sources.append({"path": m["rel"], "role": m.get("role"),
                        "sniffed_type": m.get("sniffed_type"),
                        "sha256": m.get("sha256"), "exists": m.get("exists")})

    artifacts = {}
    for name in ("status_ledger.json", "status_report.md",
                 "candidate_pool.json", "version_pairs.json"):
        p = os.path.join(args.output, name)
        artifacts[name] = {"path": name,
                           "sha256": sha256_file(p) if os.path.isfile(p)
                           else None}
    artifacts["result.json"] = {"path": "result.json", "sha256": None}

    status = "success"
    if unresolved or counts["unverifiable"] or pending_review_left or \
            reconcile.get("import_inconsistent") or \
            summary.get("missing_materials") or \
            not summary.get("task_md", {}).get("present"):
        status = "partial"

    checks = [
        {"check": "contract_fields_present", "passed": True},
        {"check": "severe_records_excluded_from_pool",
         "passed": not any(c["primary_record_id"] in severe_ids
                           for c in candidates)},
        {"check": "every_severe_flagged_has_evidence",
         "passed": all(any(s["evidence_locator"] for s in e["signals"]
                           if s["severity"] in ("severe", "flagged"))
                       for e in ledger
                       if e["status_class"] in ("severe", "flagged"))},
    ]

    result = {
        "case_id": summary.get("case_id"),
        "skill_name": SKILL_NAME,
        "engine_version": VERSION,
        "status": status,
        "artifacts": artifacts,
        "sources": sources,
        "uncertainty": uncertainty,
        "change_records": change_records,
        "counts": counts,
        "checks": checks,
        "unresolved_contract_fields": unresolved,
    }
    result.update(contract_values)
    write_json(os.path.join(args.output, "result.json"), result)
    sys.stdout.write("finalize: status=%s counts=%s unresolved=%s\n"
                     % (status, json.dumps(counts, sort_keys=True),
                        unresolved))
    return 0


# --------------------------------------------------------------------------
# Self-check (selfcheck)
# --------------------------------------------------------------------------
def cmd_selfcheck(args):
    out = args.output
    work = args.work
    failures = []

    def check(name, ok, detail=""):
        sys.stdout.write("%s %s %s\n" % ("PASS" if ok else "FAIL", name,
                                         detail))
        if not ok:
            failures.append(name)

    result_path = os.path.join(out, "result.json")
    if not os.path.isfile(result_path):
        sys.stdout.write("FAIL result_json_exists\n")
        return 1
    result = json.loads(read_bytes(result_path).decode("utf-8"))
    ledger = json.loads(read_bytes(os.path.join(out, "status_ledger.json"))
                        .decode("utf-8"))
    pool = json.loads(read_bytes(os.path.join(out, "candidate_pool.json"))
                      .decode("utf-8"))
    records = read_jsonl(os.path.join(work, "normalized.jsonl"))
    case, _ = load_case(args.input)
    contract = case.get("output_contract") or {}

    check("result_has_case_id", bool(result.get("case_id")))
    missing = [f for f in contract if f not in result]
    check("contract_keys_present", not missing, "missing=%s" % missing)
    unresolved = result.get("unresolved_contract_fields") or []
    for f in unresolved:
        check("unresolved_field_is_null[%s]" % f, result.get(f) is None)

    entries = ledger.get("records") or []
    bad_ev = [e["record_id"] for e in entries
              if e["status_class"] in ("severe", "flagged") and
              not any(s.get("evidence_locator") for s in e["signals"]
                      if s["severity"] in ("severe", "flagged"))]
    check("severe_flagged_have_evidence_locators", not bad_ev,
          "offenders=%s" % bad_ev)

    counts = result.get("counts") or {}
    recompute = {
        "records_scanned": len(entries),
        "severe": sum(1 for e in entries if e["status_class"] == "severe"),
        "flagged": sum(1 for e in entries if e["status_class"] == "flagged"),
        "unverifiable": sum(1 for e in entries
                            if e["status_class"] == "unverifiable"),
    }
    ok_counts = all(counts.get(k) == v for k, v in recompute.items())
    check("counts_recompute", ok_counts,
          "result=%s recomputed=%s" % (counts, recompute))

    severe_ids = {e["record_id"] for e in entries
                  if e["status_class"] == "severe"}
    pool_ids = {c["primary_record_id"] for c in pool.get("candidates") or []}
    for alt in [c.get("alternate_version")
                for c in pool.get("candidates") or []]:
        if alt:
            pool_ids.add(alt["record_id"])
    check("no_severe_in_candidate_pool",
          not (severe_ids & pool_ids),
          "leak=%s" % sorted(severe_ids & pool_ids))

    # no silent drops: every normalized record accounted for
    accounted = set(pool_ids)
    accounted |= {e["record_id"] for e in pool.get("excluded") or []}
    accounted |= set(pool.get("unverifiable_not_included") or [])
    accounted |= set((pool.get("folded_preprints") or {}).keys())
    all_ids = {r["record_id"] for r in records}
    check("no_silent_drops", accounted == all_ids,
          "missing=%s extra=%s" % (sorted(all_ids - accounted),
                                   sorted(accounted - all_ids)))
    check("ledger_covers_all_records",
          {e["record_id"] for e in entries} == all_ids)

    sys.stdout.write("selfcheck: %s\n"
                     % ("ALL PASS" if not failures
                        else "FAILURES: %s" % failures))
    return 0 if not failures else 1


# --------------------------------------------------------------------------
# run-all
# --------------------------------------------------------------------------
def cmd_run_all(args):
    rc = cmd_parse(args)
    if rc:
        return rc
    rc = cmd_scan(args)
    if rc:
        return rc
    rc = cmd_pair(args)
    if rc:
        return rc
    rc = cmd_reconcile(args)
    if rc:
        return rc
    if getattr(args, "dispositions", None):
        rc = cmd_adjudicate(args)
        if rc:
            sys.stderr.write("run-all: dispositions partially invalid; "
                             "continuing with applied subset (honest "
                             "degradation)\n")
    else:
        sys.stdout.write("run-all: no --dispositions given; flagged records "
                         "remain pending_model_review (status will be "
                         "partial)\n")
    rc = cmd_finalize(args)
    if rc:
        return rc
    sc = cmd_selfcheck(args)
    if sc:
        sys.stderr.write("run-all: selfcheck FAILED — treat outputs as "
                         "suspect\n")
        return 1
    return 0


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def build_parser():
    p = argparse.ArgumentParser(
        prog="status_hygiene.py",
        description="文献状态卫生与版本归并引擎：撤回/勘误/关注声明/导入撤回"
                    "治理 + preprint↔VoR 归并。纯标准库，完全离线，确定性。")
    p.add_argument("--version", action="version",
                   version="%s %s" % (SKILL_NAME, VERSION))
    sub = p.add_subparsers(dest="command")

    def add_io(sp):
        sp.add_argument("--input", default="/input",
                        help="case 目录（含 case.json / task.md / materials）")
        sp.add_argument("--work", default="/app/work", help="中间产物目录")
        sp.add_argument("--output", default="/app/output", help="交付物目录")

    for name in ("parse", "scan", "pair", "reconcile", "adjudicate",
                 "finalize", "selfcheck"):
        sp = sub.add_parser(name)
        add_io(sp)
        if name == "adjudicate":
            sp.add_argument("--dispositions", required=True,
                            help="模型撰写的 dispositions.json")
    sp = sub.add_parser("run-all", help="端到端运行全部子命令")
    add_io(sp)
    sp.add_argument("--dispositions", default=None,
                    help="可选：模型撰写的 dispositions.json")
    return p


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 0
    handlers = {
        "parse": cmd_parse, "scan": cmd_scan, "pair": cmd_pair,
        "reconcile": cmd_reconcile, "adjudicate": cmd_adjudicate,
        "finalize": cmd_finalize, "selfcheck": cmd_selfcheck,
        "run-all": cmd_run_all,
    }
    try:
        return handlers[args.command](args) or 0
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 - honest degradation
        sys.stderr.write("DEGRADED: unexpected internal error: %r\n" % exc)
        try:
            os.makedirs(args.output, exist_ok=True)
            write_json(os.path.join(args.output, "result.json"), {
                "case_id": None,
                "skill_name": SKILL_NAME,
                "engine_version": VERSION,
                "status": "degraded",
                "uncertainty": [{"kind": "internal_error",
                                 "statement": repr(exc)}],
                "unresolved_contract_fields": ["*"],
            })
        except Exception:  # noqa: BLE001
            pass
        return 2


if __name__ == "__main__":
    sys.exit(main())
