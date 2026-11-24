#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
source_gate.py — Upstream Data Authenticity Gate (上游数据真实性门控)

Part of skill bundle "source-authenticity-gate" for the Bohrium Playground
challenge "多数据库联合检索" (multi-database joint literature retrieval).

Philosophy: nothing downstream (normalize / dedup / merge) may consume a
record until its source artifact has passed an authenticity gate. This script
authenticates EVERY input artifact BEFORE any merge:

  1. Intake: read case.json + task.md; record sha256 / size / BOM / UTF-8 /
     U+FFFD for every discovered material file. Materials are discovered by
     scanning the case directory (sorted order) AND by parsing file
     references inside case.json; fixed filenames are never assumed.
  2. Format sniffing & classification: crossref / europepmc / publisher /
     reference_graph / import_state / unknown.
  3. Schema authentication per type (envelope keys, item-level required
     fields, type checks, truncation detection, HTML residue, duplicate
     identifiers inside a single payload).
  4. Cross-artifact consistency (reference-graph edges vs identifier
     universe; import_state entries vs corresponding source responses).
  5. Verdicts per artifact: trusted / trusted_with_warnings / quarantined,
     with machine-readable reason codes. Only records from trusted(+/-warnings)
     artifacts enter gated_records.json.

Stdlib only. No network, no randomness, no wall-clock in artifacts.
Deterministic (sorted scans, sorted JSON keys) and idempotent (rerun
overwrites). Run ids are derived from input content hashes.

CLI:
  --case  (default /input/case.json)
  --task  (default /input/task.md)
  --work  (default /app/work)
  --out   (default /app/output)

Exit codes:
  0  ok (status "success" or honest "partial")
  2  honest degradation (unexpected internal error; partial result written)
  3  invalid input (case.json missing / unreadable / not JSON)
"""

import argparse
import hashlib
import json
import os
import re
import sys

VERSION = "1.0.0"

# --------------------------------------------------------------------------
# Reason codes (see references/reason-codes.md). severity: info|warning|error
# Any error-severity check on an artifact => artifact is quarantined.
# Any warning-severity check (and no error) => trusted_with_warnings.
# --------------------------------------------------------------------------
REASON_SEVERITY = {
    "MATERIAL_MISSING": "error",
    "READ_ERROR": "error",
    "ENCODING_NON_UTF8": "error",
    "PARSE_ERROR": "error",
    "UNKNOWN_FORMAT": "error",
    "ENVELOPE_MISSING_KEYS": "error",
    "ENCODING_BOM": "info",
    "REPLACEMENT_CHAR_PRESENT": "warning",
    "TRAILING_CONTENT": "warning",
    "ENVELOPE_STATUS_NOT_OK": "warning",
    "COUNT_MISMATCH": "warning",
    "ITEM_FIELD_MISSING": "warning",
    "FIELD_TYPE_MISMATCH": "warning",
    "HTML_RESIDUE": "warning",
    "HTML_FORMAT_LIMITED": "info",
    "DUPLICATE_IDENTIFIER": "warning",
    "EMPTY_PAYLOAD": "warning",
    "DANGLING_EDGE": "warning",
    "IMPORT_NOT_VERIFIABLE": "warning",
    "IMPORT_INCONSISTENT": "warning",
    "TASK_FILE_MISSING": "warning",
    "ARTIFACT_QUARANTINED": "error",
}

CLASS_RECORD_SOURCES = ("crossref", "europepmc", "publisher")

DOI_RE = re.compile(r"10\.\d{4,9}/[^\s\"'<>\)\]}]+")
HTML_TAG_RE = re.compile(r"<[^>]+>")

# Item-level required fields per source type.
ITEM_REQUIRED = {
    "crossref": ["DOI", "title", "issued"],
    "europepmc": ["id", "source", "title"],
    "publisher": [],  # special rule: doi OR title
}


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------
def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def dump_json(obj):
    """Canonical deterministic JSON serialization."""
    return json.dumps(obj, ensure_ascii=False, sort_keys=True,
                      indent=2) + "\n"


def write_text(path, text):
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def rel_posix(path, base):
    """Relative POSIX-style path; never an absolute path inside artifacts."""
    try:
        rel = os.path.relpath(path, base)
    except ValueError:
        rel = os.path.basename(path)
    return rel.replace(os.sep, "/")


def normalize_identifier(value):
    """Normalize an identifier for cross-artifact comparison.

    Lowercases, strips whitespace, and removes common DOI URL/prefix
    decorations so that '10.x/y', 'doi:10.x/y' and
    'https://doi.org/10.x/y' compare equal.
    """
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    low = s.lower()
    for prefix in ("https://doi.org/", "http://doi.org/",
                   "https://dx.doi.org/", "http://dx.doi.org/", "doi:"):
        if low.startswith(prefix):
            s = s[len(prefix):]
            low = s.lower()
            break
    return low.strip()


def normalize_db_name(value):
    if value is None:
        return ""
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def strip_html(text):
    """Strip HTML tags for INSPECTION only; raw value is always kept."""
    return HTML_TAG_RE.sub(" ", text)


def check(code, detail, locator=None):
    c = {"code": code, "severity": REASON_SEVERITY.get(code, "warning"),
         "detail": detail}
    if locator is not None:
        c["locator"] = locator
    return c


# --------------------------------------------------------------------------
# Intake
# --------------------------------------------------------------------------
def read_raw(path):
    """Read a file as bytes; return (raw_bytes, error_str_or_None)."""
    try:
        with open(path, "rb") as fh:
            return fh.read(), None
    except OSError as exc:
        return None, str(exc)


def probe_bytes(raw):
    """Return encoding probe facts for a byte string."""
    info = {"size_bytes": len(raw), "bom": False, "utf8_ok": True,
            "replacement_char_count": 0}
    body = raw
    if raw.startswith(b"\xef\xbb\xbf"):
        info["bom"] = True
        body = raw[3:]
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        info["utf8_ok"] = False
        text = body.decode("utf-8", errors="replace")
    info["replacement_char_count"] = text.count("�")
    info["text"] = text
    return info


def discover_material_paths(case_path, case_obj, task_path):
    """Discover candidate material files.

    1) Recursively scan the case directory (sorted order), excluding
       case.json itself, the task file, and hidden entries.
    2) Parse file references inside case.json ("materials" entries that are
       strings or objects with path/file/filename keys).
    Returns (existing_paths_sorted, referenced_but_missing_sorted).
    """
    case_dir = os.path.dirname(os.path.abspath(case_path))
    case_abs = os.path.abspath(case_path)
    task_abs = os.path.abspath(task_path) if task_path else None

    found = set()
    for root, dirs, files in os.walk(case_dir):
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        for name in sorted(files):
            if name.startswith("."):
                continue
            p = os.path.join(root, name)
            ap = os.path.abspath(p)
            if ap == case_abs or (task_abs and ap == task_abs):
                continue
            found.add(ap)

    referenced = []
    mats = case_obj.get("materials") if isinstance(case_obj, dict) else None
    if isinstance(mats, list):
        for entry in mats:
            ref = None
            if isinstance(entry, str):
                ref = entry
            elif isinstance(entry, dict):
                for key in ("path", "file", "filename", "name"):
                    if isinstance(entry.get(key), str):
                        ref = entry[key]
                        break
            if ref:
                referenced.append(ref)

    missing = []
    for ref in referenced:
        cand = ref if os.path.isabs(ref) else os.path.join(case_dir, ref)
        ap = os.path.abspath(cand)
        if os.path.isfile(ap):
            found.add(ap)
        else:
            missing.append(rel_posix(ap, case_dir))

    return sorted(found), sorted(set(missing)), case_dir


# --------------------------------------------------------------------------
# Format sniffing & classification
# --------------------------------------------------------------------------
def looks_like_html(text):
    head = text.lstrip()[:512].lower()
    return (head.startswith("<!doctype") or head.startswith("<html")
            or bool(re.search(r"<(div|article|section|span|p|meta|body|head)"
                              r"[\s>]", head)))


def sniff_classify(text):
    """Return (classification, parsed_or_None, checks, fmt_detail).

    classification in {crossref, europepmc, publisher, reference_graph,
                       import_state, unknown}
    fmt_detail: json | jsonl | html | none
    """
    checks = []
    stripped = text.strip()
    if not stripped:
        return "unknown", None, [check("EMPTY_PAYLOAD",
                                       "material file is empty")], "none"

    # --- whole-document JSON ---
    parsed = None
    parse_err = None
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError as exc:
        parse_err = exc

    if parsed is None and parse_err is not None:
        # --- try JSONL (every non-empty line a JSON object) ---
        lines = [ln for ln in stripped.splitlines() if ln.strip()]
        jsonl_ok = bool(lines)
        jsonl_objs = []
        for ln in lines:
            try:
                obj = json.loads(ln)
                if not isinstance(obj, dict):
                    jsonl_ok = False
                    break
                jsonl_objs.append(obj)
            except json.JSONDecodeError:
                jsonl_ok = False
                break
        if jsonl_ok and jsonl_objs:
            cls = classify_records(jsonl_objs)
            if cls == "publisher":
                return "publisher", jsonl_objs, checks, "jsonl"
        # --- try HTML fragment ---
        if looks_like_html(stripped):
            return "publisher", None, checks, "html"
        return "unknown", None, [check(
            "PARSE_ERROR",
            "not parseable as JSON/JSONL and not recognisable HTML: %s"
            % parse_err)], "none"

    if isinstance(parsed, dict):
        cls = classify_object(parsed)
        if cls == "unknown":
            checks.append(check(
                "UNKNOWN_FORMAT",
                "JSON object matches no known source envelope"))
        return cls, parsed, checks, "json"
    if isinstance(parsed, list):
        cls = classify_records(parsed)
        if cls == "unknown":
            checks.append(check(
                "UNKNOWN_FORMAT",
                "JSON array matches no known record shape"))
        return cls, parsed, checks, "json"
    checks.append(check("UNKNOWN_FORMAT",
                        "top-level JSON value is neither object nor array"))
    return "unknown", parsed, checks, "json"


def classify_object(obj):
    """Classify a parsed JSON object by envelope shape."""
    msg = obj.get("message")
    if isinstance(msg, dict) and isinstance(msg.get("items"), list):
        return "crossref"
    if "resultList" in obj or "hitCount" in obj:
        return "europepmc"
    if isinstance(obj.get("nodes"), list) or isinstance(obj.get("edges"),
                                                       list):
        return "reference_graph"
    if isinstance(obj.get("records"), list) or isinstance(
            obj.get("imported"), list) or "db" in obj:
        recs = obj.get("records") or obj.get("imported")
        if isinstance(recs, list) and (not recs or isinstance(recs[0], dict)):
            return "import_state"
        if isinstance(obj.get("db"), str):
            return "import_state"
    return "unknown"


def classify_records(items):
    """Classify a list of record-like dicts (publisher payload)."""
    if not items:
        return "publisher"
    if not all(isinstance(it, dict) for it in items):
        return "unknown"
    hits = 0
    for it in items:
        keys = {str(k).lower() for k in it.keys()}
        if ("doi" in keys or "title" in keys) and (
                keys & {"authors", "author", "journal", "year", "volume",
                        "pages", "title", "doi"}):
            hits += 1
    return "publisher" if hits == len(items) else "unknown"


# --------------------------------------------------------------------------
# Schema authentication per type
# --------------------------------------------------------------------------
def auth_crossref(parsed, artifact):
    checks = []
    records = []
    excluded = []
    identifiers = set()
    msg = parsed.get("message")
    if not isinstance(msg, dict):
        checks.append(check("ENVELOPE_MISSING_KEYS",
                            'crossref envelope lacks object key "message"'))
        return checks, records, excluded, identifiers
    if parsed.get("status") != "ok":
        checks.append(check("ENVELOPE_STATUS_NOT_OK",
                            'crossref "status" is %r, expected "ok"'
                            % parsed.get("status")))
    items = msg.get("items")
    if not isinstance(items, list):
        checks.append(check("ENVELOPE_MISSING_KEYS",
                            'crossref "message.items" is not a list'))
        return checks, records, excluded, identifiers
    total = msg.get("total-results")
    if isinstance(total, int) and total > len(items):
        checks.append(check(
            "COUNT_MISMATCH",
            "message.total-results=%d but only %d items present; "
            "payload may be truncated" % (total, len(items)),
            locator="message"))
    seen_dois = {}
    for i, item in enumerate(items):
        loc = "message.items[%d]" % i
        if not isinstance(item, dict):
            checks.append(check("FIELD_TYPE_MISMATCH",
                                "item is not a JSON object", locator=loc))
            excluded.append({"locator": loc,
                             "reason_code": "FIELD_TYPE_MISMATCH"})
            continue
        for field in ITEM_REQUIRED["crossref"]:
            if field not in item or item.get(field) in (None, "", []):
                checks.append(check("ITEM_FIELD_MISSING",
                                    "required field %r missing/empty" % field,
                                    locator=loc))
        if any(f not in item or item.get(f) in (None, "", [])
               for f in ITEM_REQUIRED["crossref"]):
            excluded.append({"locator": loc,
                             "reason_code": "ITEM_FIELD_MISSING"})
            continue
        doi = item.get("DOI")
        if not isinstance(doi, str):
            checks.append(check("FIELD_TYPE_MISMATCH",
                                "DOI is not a string", locator=loc))
        nd = normalize_identifier(doi)
        if nd:
            if nd in seen_dois:
                checks.append(check(
                    "DUPLICATE_IDENTIFIER",
                    "DOI %r also at %s" % (nd, seen_dois[nd]), locator=loc))
            else:
                seen_dois[nd] = loc
            identifiers.add(nd)
        title = item.get("title")
        if isinstance(title, list):
            title = title[0] if title else None
        year = None
        issued = item.get("issued")
        if isinstance(issued, dict):
            dp = issued.get("date-parts")
            if isinstance(dp, list) and dp and isinstance(dp[0], list) \
                    and dp[0]:
                year = dp[0][0]
        abstract = item.get("abstract")
        if isinstance(abstract, str) and HTML_TAG_RE.search(abstract):
            checks.append(check("HTML_RESIDUE",
                                "HTML tag residue in abstract (raw kept; "
                                "stripped copy used for inspection)",
                                locator=loc + ".abstract"))
        records.append({
            "source_type": "crossref",
            "locator": loc,
            "identifiers": {"doi": nd} if nd else {},
            "title": title,
            "year": year,
            "container": (item.get("container-title") or [None])[0]
            if isinstance(item.get("container-title"), list)
            else item.get("container-title"),
        })
    if not items:
        checks.append(check("EMPTY_PAYLOAD",
                            "crossref message.items is empty",
                            locator="message.items"))
    return checks, records, excluded, identifiers


def auth_europepmc(parsed, artifact):
    checks = []
    records = []
    excluded = []
    identifiers = set()
    rl = parsed.get("resultList")
    results = None
    if isinstance(rl, dict) and isinstance(rl.get("result"), list):
        results = rl["result"]
        base = "resultList.result"
    elif isinstance(parsed.get("result"), list):
        results = parsed["result"]
        base = "result"
    if results is None:
        checks.append(check(
            "ENVELOPE_MISSING_KEYS",
            'europepmc envelope lacks "resultList.result" list'))
        return checks, records, excluded, identifiers
    hit = parsed.get("hitCount")
    try:
        hitn = int(hit) if hit is not None else None
    except (TypeError, ValueError):
        hitn = None
        checks.append(check("FIELD_TYPE_MISMATCH",
                            "hitCount is not an integer", locator="hitCount"))
    if hitn is not None and hitn != len(results):
        checks.append(check(
            "COUNT_MISMATCH",
            "hitCount=%d but resultList contains %d results; "
            "payload may be truncated or inconsistent" % (hitn, len(results))))
    seen_ids = {}
    for i, item in enumerate(results):
        loc = "%s[%d]" % (base, i)
        if not isinstance(item, dict):
            checks.append(check("FIELD_TYPE_MISMATCH",
                                "result is not a JSON object", locator=loc))
            excluded.append({"locator": loc,
                             "reason_code": "FIELD_TYPE_MISMATCH"})
            continue
        missing = [f for f in ITEM_REQUIRED["europepmc"]
                   if f not in item or item.get(f) in (None, "", [])]
        for f in missing:
            checks.append(check("ITEM_FIELD_MISSING",
                                "required field %r missing/empty" % f,
                                locator=loc))
        if missing:
            excluded.append({"locator": loc,
                             "reason_code": "ITEM_FIELD_MISSING"})
            continue
        ids = {}
        for key in ("id", "pmid", "pmcid", "doi"):
            v = item.get(key)
            if v not in (None, ""):
                nv = normalize_identifier(v)
                ids[key] = nv
                identifiers.add(nv)
        prim = normalize_identifier(item.get("id"))
        if prim:
            if prim in seen_ids:
                checks.append(check(
                    "DUPLICATE_IDENTIFIER",
                    "id %r also at %s" % (prim, seen_ids[prim]), locator=loc))
            else:
                seen_ids[prim] = loc
        absv = item.get("abstractText")
        if isinstance(absv, str) and HTML_TAG_RE.search(absv):
            checks.append(check("HTML_RESIDUE",
                                "HTML tag residue in abstractText (raw "
                                "kept; stripped copy used for inspection)",
                                locator=loc + ".abstractText"))
        records.append({
            "source_type": "europepmc",
            "locator": loc,
            "identifiers": ids,
            "title": item.get("title"),
            "year": item.get("pubYear"),
            "container": item.get("journalTitle"),
        })
    if not results:
        checks.append(check("EMPTY_PAYLOAD",
                            "europepmc result list is empty", locator=base))
    return checks, records, excluded, identifiers


def auth_publisher(parsed, fmt, artifact, raw_text):
    checks = []
    records = []
    excluded = []
    identifiers = set()
    if fmt == "html":
        checks.append(check(
            "HTML_FORMAT_LIMITED",
            "publisher payload is an HTML fragment; only DOI-level "
            "identifiers can be gated (structure not machine-verifiable)"))
        text_for_scan = raw_text
        dois = sorted(set(normalize_identifier(m)
                          for m in DOI_RE.findall(text_for_scan)))
        for i, d in enumerate(dois):
            identifiers.add(d)
            records.append({
                "source_type": "publisher",
                "locator": "html_body.doi_match[%d]" % i,
                "identifiers": {"doi": d},
                "title": None,
                "year": None,
                "container": None,
            })
        if not dois:
            checks.append(check("EMPTY_PAYLOAD",
                                "no DOI-like identifier found in HTML "
                                "fragment"))
        return checks, records, excluded, identifiers

    items = parsed if isinstance(parsed, list) else []
    base = "line" if fmt == "jsonl" else ""
    seen_dois = {}
    for i, item in enumerate(items):
        loc = ("%s[%d]" % (base, i)) if base else "[%d]" % i
        if not isinstance(item, dict):
            checks.append(check("FIELD_TYPE_MISMATCH",
                                "record is not a JSON object", locator=loc))
            excluded.append({"locator": loc,
                             "reason_code": "FIELD_TYPE_MISMATCH"})
            continue
        low = {str(k).lower(): v for k, v in item.items()}
        doi = low.get("doi")
        title = low.get("title")
        if (doi in (None, "")) and (title in (None, "")):
            checks.append(check("ITEM_FIELD_MISSING",
                                "publisher record needs 'doi' or 'title'; "
                                "both missing/empty", locator=loc))
            excluded.append({"locator": loc,
                             "reason_code": "ITEM_FIELD_MISSING"})
            continue
        ids = {}
        nd = normalize_identifier(doi)
        if nd:
            if nd in seen_dois:
                checks.append(check(
                    "DUPLICATE_IDENTIFIER",
                    "DOI %r also at %s" % (nd, seen_dois[nd]), locator=loc))
            else:
                seen_dois[nd] = loc
            ids["doi"] = nd
            identifiers.add(nd)
        absv = low.get("abstract")
        if isinstance(absv, str) and HTML_TAG_RE.search(absv):
            checks.append(check("HTML_RESIDUE",
                                "HTML tag residue in abstract (raw kept; "
                                "stripped copy used for inspection)",
                                locator=loc + ".abstract"))
        year = low.get("year")
        if year is not None and not isinstance(year, (int, str)):
            checks.append(check("FIELD_TYPE_MISMATCH",
                                "year has unexpected type %s"
                                % type(year).__name__, locator=loc + ".year"))
        records.append({
            "source_type": "publisher",
            "locator": loc,
            "identifiers": ids,
            "title": title,
            "year": year,
            "container": low.get("journal"),
        })
    if not items:
        checks.append(check("EMPTY_PAYLOAD",
                            "publisher payload contains zero records"))
    return checks, records, excluded, identifiers


def auth_reference_graph(parsed):
    """Return (checks, edges, node_identifiers)."""
    checks = []
    edges = []
    node_ids = set()
    nodes = parsed.get("nodes")
    raw_edges = parsed.get("edges")
    if not isinstance(nodes, list) and not isinstance(raw_edges, list):
        checks.append(check(
            "ENVELOPE_MISSING_KEYS",
            'reference_graph has neither "nodes" nor "edges" list'))
        return checks, edges, node_ids
    if isinstance(nodes, list):
        for i, node in enumerate(nodes):
            loc = "nodes[%d]" % i
            if not isinstance(node, dict):
                checks.append(check("FIELD_TYPE_MISMATCH",
                                    "node is not a JSON object", locator=loc))
                continue
            nid = node.get("id") or node.get("identifier")
            if nid in (None, ""):
                checks.append(check("ITEM_FIELD_MISSING",
                                    "node lacks 'id'/'identifier'",
                                    locator=loc))
                continue
            node_ids.add(normalize_identifier(nid))
            for extra in ("doi", "pmid"):
                if node.get(extra):
                    node_ids.add(normalize_identifier(node[extra]))
    if isinstance(raw_edges, list):
        for i, e in enumerate(raw_edges):
            loc = "edges[%d]" % i
            if isinstance(e, dict) and "from" in e and "to" in e:
                edges.append({"locator": loc,
                              "from": normalize_identifier(e["from"]),
                              "to": normalize_identifier(e["to"])})
            elif isinstance(e, (list, tuple)) and len(e) >= 2:
                edges.append({"locator": loc,
                              "from": normalize_identifier(e[0]),
                              "to": normalize_identifier(e[1])})
            else:
                checks.append(check("FIELD_TYPE_MISMATCH",
                                    "edge is not {from,to} or a pair",
                                    locator=loc))
    return checks, edges, node_ids


def auth_import_state(parsed):
    """Return (checks, entries). entries: [{locator, db, identifier, batch}]."""
    checks = []
    entries = []
    recs = parsed.get("records")
    if recs is None:
        recs = parsed.get("imported")
    if isinstance(recs, list):
        for i, r in enumerate(recs):
            loc = ("records" if parsed.get("records") is not None
                   else "imported") + ("[%d]" % i)
            if not isinstance(r, dict):
                checks.append(check("FIELD_TYPE_MISMATCH",
                                    "import entry is not a JSON object",
                                    locator=loc))
                continue
            db = r.get("db") or r.get("source") or r.get("database")
            ident = (r.get("identifier") or r.get("id") or r.get("doi")
                     or r.get("pmid"))
            if not db or not ident:
                checks.append(check(
                    "ITEM_FIELD_MISSING",
                    "import entry needs 'db' and 'identifier'", locator=loc))
                continue
            entries.append({"locator": loc, "db": str(db),
                            "db_norm": normalize_db_name(db),
                            "identifier": str(ident),
                            "identifier_norm": normalize_identifier(ident),
                            "batch": r.get("batch")})
    elif isinstance(parsed.get("db"), str) and isinstance(
            parsed.get("identifiers"), list):
        for i, ident in enumerate(parsed["identifiers"]):
            entries.append({"locator": "identifiers[%d]" % i,
                            "db": parsed["db"],
                            "db_norm": normalize_db_name(parsed["db"]),
                            "identifier": str(ident),
                            "identifier_norm": normalize_identifier(ident),
                            "batch": parsed.get("batch")})
    else:
        checks.append(check(
            "ENVELOPE_MISSING_KEYS",
            'import_state lacks "records"/"imported" list or '
            '{"db", "identifiers"} shape'))
    if recs is not None and isinstance(recs, list) and not recs:
        checks.append(check("EMPTY_PAYLOAD", "import_state has zero entries"))
    return checks, entries


# --------------------------------------------------------------------------
# Contract handling
# --------------------------------------------------------------------------
def contract_fields(case_obj):
    """Extract top-level output_contract field names from dict/list/string."""
    oc = case_obj.get("output_contract") if isinstance(case_obj, dict) \
        else None
    if isinstance(oc, dict):
        return sorted(str(k) for k in oc.keys())
    if isinstance(oc, list):
        out = []
        for item in oc:
            if isinstance(item, str):
                out.append(item)
            elif isinstance(item, dict) and isinstance(item.get("name"),
                                                       str):
                out.append(item["name"])
        return sorted(set(out))
    if isinstance(oc, str):
        s = oc.strip()
        if not s:
            return []
        try:
            parsed = json.loads(s)
            return contract_fields({"output_contract": parsed})
        except (json.JSONDecodeError, ValueError):
            parts = re.split(r"[,\s]+", s)
            return sorted(p for p in parts if p)
    return []


def fill_contract_field(name, ctx):
    """Honestly fill a contract field, or return None (=> unresolved)."""
    n = normalize_db_name(name)
    summary = ctx["summary"]
    if "gatedrecord" in n or n in ("gatedrecords", "records"):
        return ctx["gated_records_public"]
    if "quarantin" in n:
        return [a["artifact_id"] for a in ctx["artifacts"]
                if a.get("verdict") == "quarantined"]
    if "summary" in n or "authenticity" in n:
        return summary
    if "downstreamready" in n or n == "ready":
        return summary.get("quarantined", 0) == 0
    if "ledger" in n:
        return "authenticity_ledger.json"
    if "report" in n:
        return "authenticity_report.md"
    if "uncertainty" in n:
        return ctx["uncertainty"]
    return None


# --------------------------------------------------------------------------
# Report rendering
# --------------------------------------------------------------------------
def render_report(ctx):
    L = []
    L.append("# 上游数据真实性门控报告 (Source Authenticity Report)")
    L.append("")
    L.append("- case_id: `%s`" % ctx["case_id"])
    L.append("- run_id: `%s` (derived from input content hashes)" % ctx["run_id"])
    L.append("- gate version: `%s`" % VERSION)
    L.append("- status: **%s**" % ctx["status"])
    L.append("")
    L.append("> 本报告由 scripts/source_gate.py 确定性生成；不含时间戳，"
             "重跑同一输入应得到字节级一致的输出。")
    L.append("")
    L.append("## 1. 工件级判定 (Per-artifact verdicts)")
    L.append("")
    L.append("| artifact | path | classification | verdict | records | gated | reason codes |")
    L.append("|---|---|---|---|---|---|---|")
    for a in ctx["artifacts"]:
        codes = sorted({c["code"] for c in a["checks"]}) or ["-"]
        L.append("| %s | %s | %s | **%s** | %s | %s | %s |" % (
            a["artifact_id"], a["path"], a["classification"], a["verdict"],
            a.get("record_count", "-"), a.get("gated_record_count", "-"),
            ", ".join(codes)))
    L.append("")
    L.append("## 2. 检查明细 (Check details)")
    L.append("")
    for a in ctx["artifacts"]:
        if not a["checks"]:
            continue
        L.append("### %s — `%s` (sha256 `%s…`)" % (
            a["artifact_id"], a["path"], (a.get("sha256") or "")[:12]))
        L.append("")
        for c in a["checks"]:
            loc = (" `%s`" % c["locator"]) if c.get("locator") else ""
            L.append("- **%s** [%s]%s — %s" % (
                c["code"], c["severity"], loc, c["detail"]))
        L.append("")
    L.append("## 3. 跨工件一致性 (Cross-artifact consistency)")
    L.append("")
    L.append("- 引用图边检查: %d 条边, %d 条悬挂 (dangling)" % (
        ctx["summary"]["edges_total"], ctx["summary"]["edges_dangling"]))
    ie = ctx["summary"]["import_entries"]
    L.append("- 导入状态条目: verified=%d, not_verifiable=%d, inconsistent=%d"
             % (ie["verified"], ie["not_verifiable"], ie["inconsistent"]))
    L.append("")
    L.append("## 4. 门控结论 (Gate outcome)")
    L.append("")
    s = ctx["summary"]
    L.append("- trusted: %d; trusted_with_warnings: %d; quarantined: %d"
             % (s["trusted"], s["trusted_with_warnings"], s["quarantined"]))
    L.append("- 进入 gated_records.json 的记录数: **%d**"
             % s["total_gated_records"])
    if ctx["quarantined_list"]:
        L.append("- 被隔离工件（其记录一律不得进入下游）: %s"
                 % ", ".join(ctx["quarantined_list"]))
    if ctx["unresolved_contract_fields"]:
        L.append("- 无法诚实填写的契约字段 (null): %s"
                 % ", ".join(ctx["unresolved_contract_fields"]))
    if ctx["uncertainty"]:
        L.append("")
        L.append("## 5. 不确定性声明 (Uncertainty)")
        L.append("")
        for u in ctx["uncertainty"]:
            L.append("- %s" % u)
    L.append("")
    return "\n".join(L)


# --------------------------------------------------------------------------
# Main pipeline
# --------------------------------------------------------------------------
def build_arg_parser():
    p = argparse.ArgumentParser(
        prog="source_gate.py",
        description="Upstream data authenticity gate for multi-database "
                    "joint literature retrieval cases. Authenticates every "
                    "input artifact before any downstream merge.")
    p.add_argument("--case", default="/input/case.json",
                   help="path to case.json (default: /input/case.json)")
    p.add_argument("--task", default="/input/task.md",
                   help="path to task.md (default: /input/task.md)")
    p.add_argument("--work", default="/app/work",
                   help="working directory for intermediate artifacts "
                        "(default: /app/work)")
    p.add_argument("--out", default="/app/output",
                   help="output directory (default: /app/output)")
    return p


def skeleton_result():
    return {
        "case_id": None,
        "status": "partial",
        "run_id": None,
        "sources": [],
        "uncertainty": ["gate run did not complete; this is an early "
                        "partial skeleton written before any input was "
                        "consumed"],
        "change_records": [],
        "artifacts": [],
        "unresolved_contract_fields": [],
    }


def finalize_result(ctx, out_dir):
    """Assemble and write result.json (artifacts hashed after writing)."""
    result = {
        "case_id": ctx["case_id"],
        "status": ctx["status"],
        "run_id": ctx["run_id"],
        "sources": ctx["sources"],
        "uncertainty": ctx["uncertainty"],
        "change_records": ctx["change_records"],
        "artifacts": [],  # filled below
        "unresolved_contract_fields": ctx["unresolved_contract_fields"],
        "authenticity_summary": ctx["summary"],
        "quarantined_artifacts": ctx["quarantined_list"],
        "gated_record_count": ctx["summary"].get("total_gated_records", 0),
    }
    for field in ctx["contract_fields"]:
        if field in result and result[field] not in (None, [], {}):
            continue
        value = fill_contract_field(field, ctx)
        if value is None:
            result[field] = None
            if field not in result["unresolved_contract_fields"]:
                result["unresolved_contract_fields"].append(field)
        else:
            result[field] = value
    result["unresolved_contract_fields"] = sorted(
        set(result["unresolved_contract_fields"]))

    artifacts = []
    for name in sorted(os.listdir(out_dir)):
        p = os.path.join(out_dir, name)
        if not os.path.isfile(p) or name == "result.json":
            continue
        raw, err = read_raw(p)
        if err:
            continue
        artifacts.append({"path": name, "sha256": sha256_bytes(raw)})
    artifacts.append({"path": "result.json", "sha256": None,
                      "note": "self-hash omitted to avoid self-reference; "
                              "verify by re-running the gate"})
    result["artifacts"] = artifacts
    write_text(os.path.join(out_dir, "result.json"), dump_json(result))
    return result


def run(case_path, task_path, work_dir, out_dir):
    ctx = {
        "case_id": None, "status": "partial", "run_id": None,
        "sources": [], "uncertainty": [], "change_records": [],
        "artifacts": [], "summary": {}, "quarantined_list": [],
        "unresolved_contract_fields": [], "contract_fields": [],
        "gated_records_public": [],
    }
    seq = [0]

    def record_change(action, detail):
        seq[0] += 1
        ctx["change_records"].append(
            {"seq": seq[0], "action": action, "detail": detail})

    # ---- read case.json ------------------------------------------------
    case_abs = os.path.abspath(case_path)
    raw, err = read_raw(case_abs)
    if err:
        ctx["status"] = "input_error"
        ctx["uncertainty"].append("case.json unreadable: %s" % err)
        finalize_result(ctx, out_dir)
        return 3
    case_sha = sha256_bytes(raw)
    try:
        case_obj = json.loads(raw.decode("utf-8", errors="replace"))
        if not isinstance(case_obj, dict):
            raise ValueError("top level is not a JSON object")
    except (json.JSONDecodeError, ValueError) as exc:
        ctx["status"] = "input_error"
        ctx["uncertainty"].append("case.json is not a valid JSON object: %s"
                                  % exc)
        finalize_result(ctx, out_dir)
        return 3
    ctx["case_id"] = case_obj.get("case_id") or case_obj.get("id")
    ctx["contract_fields"] = contract_fields(case_obj)
    record_change("intake_case", "case.json read (sha256 %s…); %d contract "
                  "fields declared" % (case_sha[:12],
                                       len(ctx["contract_fields"])))

    # ---- read task.md --------------------------------------------------
    task_abs = os.path.abspath(task_path)
    task_raw, task_err = read_raw(task_abs)
    task_sha = None
    if task_err:
        ctx["uncertainty"].append(
            "task file missing/unreadable (TASK_FILE_MISSING); gate "
            "proceeded using case.json only (%s)" % task_err)
        record_change("intake_task_missing",
                      "task.md unreadable: %s" % task_err)
    else:
        task_sha = sha256_bytes(task_raw)
        record_change("intake_task", "task.md read (sha256 %s…)"
                      % task_sha[:12])

    # ---- discover materials --------------------------------------------
    found, missing_refs, case_dir = discover_material_paths(
        case_abs, case_obj, task_abs)
    record_change("discover_materials",
                  "%d material files discovered by sorted directory scan + "
                  "case.json references; %d referenced but missing"
                  % (len(found), len(missing_refs)))

    artifacts = []
    for i, rel in enumerate(missing_refs):
        artifacts.append({
            "artifact_id": "art-missing-%03d" % (i + 1),
            "path": rel, "exists": False, "sha256": None, "size_bytes": 0,
            "bom": False, "utf8_ok": False, "replacement_char_count": 0,
            "classification": "unknown", "format": "none",
            "verdict": "quarantined", "record_count": 0,
            "gated_record_count": 0,
            "checks": [check("MATERIAL_MISSING",
                             "referenced in case.json but not found on "
                             "disk")],
        })
        record_change("quarantine_artifact",
                      "%s: MATERIAL_MISSING" % rel)

    # ---- per-artifact authentication ------------------------------------
    all_records = []          # candidate gated records (pre-verdict)
    excluded_items = []
    identifier_universe = set()
    idb_artifacts = {}        # db_norm -> artifact dict (source dbs)
    graph_edges_all = []
    import_entries_all = []

    for idx, path in enumerate(found):
        rel = rel_posix(path, case_dir)
        art = {"artifact_id": "art-%03d" % (idx + 1), "path": rel,
               "exists": True, "checks": [], "record_count": 0,
               "gated_record_count": 0}
        raw, err = read_raw(path)
        if err:
            art.update({"sha256": None, "size_bytes": 0, "bom": False,
                        "utf8_ok": False, "replacement_char_count": 0,
                        "classification": "unknown", "format": "none",
                        "verdict": "quarantined"})
            art["checks"].append(check("READ_ERROR", err))
            artifacts.append(art)
            record_change("quarantine_artifact", "%s: READ_ERROR" % rel)
            continue
        probe = probe_bytes(raw)
        art.update({"sha256": sha256_bytes(raw),
                    "size_bytes": probe["size_bytes"],
                    "bom": probe["bom"],
                    "utf8_ok": probe["utf8_ok"],
                    "replacement_char_count":
                        probe["replacement_char_count"]})
        if probe["bom"]:
            art["checks"].append(check(
                "ENCODING_BOM", "UTF-8 BOM present (stripped for parsing)"))
        if not probe["utf8_ok"]:
            art["checks"].append(check(
                "ENCODING_NON_UTF8",
                "file is not valid UTF-8; %d U+FFFD replacement chars after "
                "lossy decode" % probe["replacement_char_count"]))
        elif probe["replacement_char_count"]:
            art["checks"].append(check(
                "REPLACEMENT_CHAR_PRESENT",
                "%d U+FFFD replacement characters present"
                % probe["replacement_char_count"]))

        cls, parsed, sniff_checks, fmt = sniff_classify(probe["text"])
        art["checks"].extend(sniff_checks)
        art["classification"] = cls
        art["format"] = fmt

        records, excluded, identifiers = [], [], set()
        if cls == "crossref" and fmt == "json":
            c, records, excluded, identifiers = auth_crossref(parsed, art)
            art["checks"].extend(c)
        elif cls == "europepmc" and fmt == "json":
            c, records, excluded, identifiers = auth_europepmc(parsed, art)
            art["checks"].extend(c)
        elif cls == "publisher":
            c, records, excluded, identifiers = auth_publisher(
                parsed, fmt, art, probe["text"])
            art["checks"].extend(c)
        elif cls == "reference_graph" and fmt == "json":
            c, edges, node_ids = auth_reference_graph(parsed)
            art["checks"].extend(c)
            art["graph_edges"] = edges
            graph_edges_all.append((art, edges))
            identifiers = node_ids
            art["record_count"] = len(edges)
        elif cls == "import_state" and fmt == "json":
            c, entries = auth_import_state(parsed)
            art["checks"].extend(c)
            art["import_entries"] = entries
            import_entries_all.append((art, entries))
            art["record_count"] = len(entries)

        if cls in CLASS_RECORD_SOURCES:
            art["record_count"] = len(records) + len(excluded)
            art["identifiers"] = sorted(identifiers)
            idb_artifacts.setdefault(normalize_db_name(cls), art)
            identifier_universe.update(identifiers)
            for r in records:
                r = dict(r)
                r["source_artifact"] = art["artifact_id"]
                all_records.append(r)
            for ex in excluded:
                ex = dict(ex)
                ex["source_artifact"] = art["artifact_id"]
                excluded_items.append(ex)
        elif cls in ("reference_graph", "import_state"):
            identifier_universe.update(identifiers)

        artifacts.append(art)

    # ---- cross-artifact consistency -------------------------------------
    edges_total = 0
    edges_dangling = 0
    for art, edges in graph_edges_all:
        for e in edges:
            edges_total += 1
            dangling = []
            for end in ("from", "to"):
                if e[end] not in identifier_universe:
                    dangling.append(e[end])
            if dangling:
                edges_dangling += 1
                art["checks"].append(check(
                    "DANGLING_EDGE",
                    "edge endpoint(s) %s do not resolve to any identifier "
                    "present in the gated materials" % ", ".join(
                        sorted(set(dangling))),
                    locator=e["locator"]))
    if edges_total:
        record_change("check_reference_graph",
                      "%d edges checked, %d dangling (reported, not fatal)"
                      % (edges_total, edges_dangling))

    ie_stats = {"verified": 0, "not_verifiable": 0, "inconsistent": 0}
    for art, entries in import_entries_all:
        entry_results = []
        for ent in entries:
            target = idb_artifacts.get(ent["db_norm"])
            if target is None:
                ie_stats["not_verifiable"] += 1
                art["checks"].append(check(
                    "IMPORT_NOT_VERIFIABLE",
                    "entry claims import from db '%s' id '%s' but no %s "
                    "source artifact exists in this case; declared gap"
                    % (ent["db"], ent["identifier"], ent["db"]),
                    locator=ent["locator"]))
                entry_results.append({"locator": ent["locator"],
                                      "db": ent["db"],
                                      "identifier": ent["identifier"],
                                      "verdict": "not_verifiable"})
            elif ent["identifier_norm"] not in set(
                    target.get("identifiers", [])):
                ie_stats["inconsistent"] += 1
                art["checks"].append(check(
                    "IMPORT_INCONSISTENT",
                    "entry claims import from db '%s' id '%s' but that "
                    "identifier is absent from %s; entry quarantined"
                    % (ent["db"], ent["identifier"], target["artifact_id"]),
                    locator=ent["locator"]))
                entry_results.append({"locator": ent["locator"],
                                      "db": ent["db"],
                                      "identifier": ent["identifier"],
                                      "verdict": "quarantined"})
                record_change("quarantine_import_entry",
                              "%s %s: IMPORT_INCONSISTENT"
                              % (art["artifact_id"], ent["locator"]))
            else:
                ie_stats["verified"] += 1
                entry_results.append({"locator": ent["locator"],
                                      "db": ent["db"],
                                      "identifier": ent["identifier"],
                                      "verdict": "verified"})
        art["import_entry_results"] = entry_results

    # ---- verdicts ---------------------------------------------------------
    for art in artifacts:
        if art.get("verdict") == "quarantined":
            continue
        codes = {c["code"] for c in art["checks"]}
        if any(REASON_SEVERITY.get(c) == "error" for c in codes):
            art["verdict"] = "quarantined"
        elif any(REASON_SEVERITY.get(c) == "warning" for c in codes):
            art["verdict"] = "trusted_with_warnings"
        else:
            art["verdict"] = "trusted"
        if art["verdict"] == "quarantined":
            record_change("quarantine_artifact",
                          "%s (%s): %s"
                          % (art["artifact_id"], art["path"],
                             ",".join(sorted(
                                 c for c in codes
                                 if REASON_SEVERITY.get(c) == "error"))))

    quarantined_ids = {a["artifact_id"] for a in artifacts
                       if a["verdict"] == "quarantined"}
    gated = []
    for r in all_records:
        if r["source_artifact"] in quarantined_ids:
            excluded_items.append({
                "source_artifact": r["source_artifact"],
                "locator": r["locator"],
                "reason_code": "ARTIFACT_QUARANTINED",
            })
            continue
        gated.append(r)
    gated.sort(key=lambda r: (r["source_artifact"], r["locator"]))
    for i, r in enumerate(gated):
        r["record_id"] = "rec-%04d" % (i + 1)
    for art in artifacts:
        art["gated_record_count"] = sum(
            1 for r in gated if r["source_artifact"] == art["artifact_id"])

    for qid in sorted(quarantined_ids):
        qpath = next(a["path"] for a in artifacts
                     if a["artifact_id"] == qid)
        ctx["uncertainty"].append(
            "artifact %s (%s) was quarantined; its records are excluded "
            "from gated_records.json and must not reach downstream "
            "normalize/dedup/merge steps" % (qid, qpath))
    if edges_dangling:
        ctx["uncertainty"].append(
            "%d reference-graph edge(s) dangle outside the gated "
            "identifier universe; reported, not fatal" % edges_dangling)
    if ie_stats["not_verifiable"]:
        ctx["uncertainty"].append(
            "%d import_state entrie(s) are not_verifiable because the "
            "corresponding source artifact is absent (declared gap)"
            % ie_stats["not_verifiable"])
    if ie_stats["inconsistent"]:
        ctx["uncertainty"].append(
            "%d import_state entrie(s) are inconsistent with the source "
            "responses and were quarantined" % ie_stats["inconsistent"])
    for ex in excluded_items:
        record_change("exclude_item",
                      "%s %s: %s" % (ex.get("source_artifact"),
                                     ex.get("locator"),
                                     ex.get("reason_code")))

    summary = {
        "total_artifacts": len(artifacts),
        "trusted": sum(1 for a in artifacts if a["verdict"] == "trusted"),
        "trusted_with_warnings": sum(
            1 for a in artifacts
            if a["verdict"] == "trusted_with_warnings"),
        "quarantined": len(quarantined_ids),
        "total_records_seen": sum(a.get("record_count", 0) for a in artifacts
                                  if a["classification"]
                                  in CLASS_RECORD_SOURCES),
        "total_gated_records": len(gated),
        "edges_total": edges_total,
        "edges_dangling": edges_dangling,
        "import_entries": ie_stats,
    }
    ctx["summary"] = summary
    ctx["artifacts"] = artifacts
    ctx["quarantined_list"] = sorted(quarantined_ids)
    ctx["gated_records_public"] = [
        {"record_id": r["record_id"], "source_artifact": r["source_artifact"],
         "source_type": r["source_type"], "locator": r["locator"],
         "identifiers": r["identifiers"], "title": r["title"],
         "year": r["year"], "container": r["container"]}
        for r in gated
    ]

    # ---- run id (content-derived, no wall-clock) --------------------------
    run_material = ["case:%s" % case_sha,
                    "task:%s" % (task_sha or "absent")]
    for a in sorted(artifacts, key=lambda x: x["path"]):
        run_material.append("%s:%s" % (a["path"], a.get("sha256") or "none"))
    ctx["run_id"] = "gate-" + sha256_text("\n".join(run_material))[:16]

    # ---- sources ---------------------------------------------------------
    ctx["sources"] = ([{"path": os.path.basename(case_abs),
                        "role": "case", "sha256": case_sha}] +
                      ([{"path": os.path.basename(task_abs), "role": "task",
                         "sha256": task_sha}] if task_sha else []) +
                      [{"path": a["path"], "role": "material",
                        "artifact_id": a["artifact_id"],
                        "sha256": a.get("sha256"),
                        "verdict": a["verdict"]}
                       for a in artifacts])

    # ---- contract pre-check: which fields can be filled honestly ----------
    base_fields = ("case_id", "status", "sources", "uncertainty",
                   "change_records", "artifacts")
    unfilled = sorted(f for f in ctx["contract_fields"]
                      if f not in base_fields
                      and fill_contract_field(f, ctx) is None)
    ctx["unresolved_contract_fields"] = unfilled
    if unfilled:
        ctx["uncertainty"].append(
            "contract field(s) %s could not be filled honestly and are "
            "null (see unresolved_contract_fields)" % ", ".join(unfilled))

    # ---- status -----------------------------------------------------------
    if ctx["unresolved_contract_fields"] or quarantined_ids or task_err:
        ctx["status"] = "partial"
    else:
        ctx["status"] = "success"

    # ---- write work artifact (intake manifest) ----------------------------
    os.makedirs(work_dir, exist_ok=True)
    manifest = {"run_id": ctx["run_id"], "case_id": ctx["case_id"],
                "intake": [{"path": a["path"], "sha256": a.get("sha256"),
                            "size_bytes": a.get("size_bytes"),
                            "bom": a.get("bom"), "utf8_ok": a.get("utf8_ok"),
                            "replacement_char_count":
                                a.get("replacement_char_count"),
                            "classification": a["classification"],
                            "verdict": a["verdict"]}
                           for a in artifacts]}
    write_text(os.path.join(work_dir, "intake_manifest.json"),
               dump_json(manifest))

    # ---- write outputs ------------------------------------------------------
    ledger = {"run_id": ctx["run_id"], "case_id": ctx["case_id"],
              "gate_version": VERSION,
              "artifacts": artifacts, "summary": summary}
    write_text(os.path.join(out_dir, "authenticity_ledger.json"),
               dump_json(ledger))
    record_change("write_output", "authenticity_ledger.json")

    gated_doc = {"run_id": ctx["run_id"], "case_id": ctx["case_id"],
                 "gate_version": VERSION,
                 "record_count": len(gated),
                 "records": ctx["gated_records_public"],
                 "excluded_items": sorted(
                     excluded_items,
                     key=lambda e: (str(e.get("source_artifact")),
                                    str(e.get("locator")))),
                 "quarantined_artifacts": [
                     {"artifact_id": a["artifact_id"], "path": a["path"],
                      "reason_codes": sorted(
                          {c["code"] for c in a["checks"]
                           if REASON_SEVERITY.get(c["code"]) == "error"})}
                     for a in artifacts if a["verdict"] == "quarantined"]}
    write_text(os.path.join(out_dir, "gated_records.json"),
               dump_json(gated_doc))
    record_change("write_output", "gated_records.json")

    write_text(os.path.join(out_dir, "authenticity_report.md"),
               render_report(ctx))
    record_change("write_output", "authenticity_report.md")

    finalize_result(ctx, out_dir)
    return 0


def main(argv=None):
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    out_dir = os.path.abspath(args.out)
    work_dir = os.path.abspath(args.work)

    # ---- STEP 0 FIRST: create out dir and write honest partial skeleton ---
    try:
        os.makedirs(out_dir, exist_ok=True)
        write_text(os.path.join(out_dir, "result.json"),
                   dump_json(skeleton_result()))
    except OSError as exc:
        sys.stderr.write("FATAL: cannot create output directory or write "
                         "result.json skeleton: %s\n" % exc)
        return 2

    try:
        return run(args.case, args.task, work_dir, out_dir)
    except Exception as exc:  # honest degradation, never a traceback crash
        try:
            ctx = {"case_id": None, "status": "partial", "run_id": None,
                   "sources": [],
                   "uncertainty": ["unexpected internal error; gate aborted "
                                   "with honest partial result: %s: %s"
                                   % (type(exc).__name__, exc)],
                   "change_records": [], "summary": {},
                   "quarantined_list": [], "unresolved_contract_fields": [],
                   "contract_fields": [], "gated_records_public": []}
            finalize_result(ctx, out_dir)
        except Exception:
            pass
        sys.stderr.write("DEGRADED: %s: %s\n" % (type(exc).__name__, exc))
        return 2


if __name__ == "__main__":
    sys.exit(main())
