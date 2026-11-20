#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared utilities for the rob-signal-dual-adjudicator skill.

Standard library only, Python >= 3.8. No network access.
"""
import hashlib
import json
import os
import re
import unicodedata

JUDGMENT_LEVELS = ["present", "likely", "no_indication", "insufficient"]
# Higher rank = higher risk. Used by the conservative adjudication rule.
RISK_RANK = {"present": 3, "likely": 2, "no_indication": 1, "insufficient": 0}


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------

def normalize(text):
    """Normalize text for verbatim quote matching.

    - NFKC fold (full-width -> half-width, compatibility chars)
    - join hyphen line breaks ("exam-\\nple" -> "example")
    - collapse all whitespace to single spaces
    """
    if text is None:
        return ""
    text = unicodedata.normalize("NFKC", text)
    # join soft hyphen line breaks and ASCII hyphen-newline breaks
    text = re.sub(r"[-\u00ad]\s*\n\s*", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def norm_contains(haystack, needle):
    """Normalized substring match."""
    n = normalize(needle)
    if not n:
        return False
    return n in normalize(haystack)


# ---------------------------------------------------------------------------
# JSONL / IO helpers
# ---------------------------------------------------------------------------

def read_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def write_json(path, obj):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def read_jsonl(path):
    rows = []
    if not os.path.exists(path):
        return rows
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                rows.append({"_parse_error": True, "raw": line[:500]})
    return rows


def append_jsonl(path, row):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_jsonl(path, rows):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def sha256_file(path):
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return None


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()


def word_count(text):
    if not text:
        return 0
    # count CJK chars individually plus latin word tokens
    cjk = re.findall(r"[\u4e00-\u9fff]", text)
    latin = re.findall(r"[A-Za-z0-9]+", text)
    return len(cjk) + len(latin)


# ---------------------------------------------------------------------------
# Defensive case.json parsing
# ---------------------------------------------------------------------------

DOC_LIST_KEYS = ["documents", "papers", "references", "files",
                 "literature", "corpus", "materials"]
CONTRACT_KEYS = ["output_contract", "contract", "output_fields",
                 "required_fields"]
CASE_ID_KEYS = ["case_id", "id", "caseId"]


def deep_find(obj, keys, depth=0, max_depth=8):
    """Recursively find the first value whose key matches any of `keys`.

    Returns (key, value) or (None, None).
    """
    if depth > max_depth:
        return None, None
    if isinstance(obj, dict):
        for k in keys:
            if k in obj:
                return k, obj[k]
        for v in obj.values():
            found_key, found_val = deep_find(v, keys, depth + 1, max_depth)
            if found_key is not None:
                return found_key, found_val
    elif isinstance(obj, list):
        for item in obj:
            found_key, found_val = deep_find(item, keys, depth + 1, max_depth)
            if found_key is not None:
                return found_key, found_val
    return None, None


def parse_case(case_path):
    """Defensively parse case.json. Never raises; returns a dict with
    case_id, doc_entries (raw list or None), output_contract, uncertainties.
    """
    out = {"case_id": "unknown_case", "doc_entries": None,
           "output_contract": None, "uncertainties": [], "raw_case": None}
    raw = read_json(case_path, default=None)
    if raw is None:
        out["uncertainties"].append(
            "case.json missing or unparseable at %s; fell back to directory scan"
            % case_path)
        return out
    out["raw_case"] = raw

    # case_id
    if isinstance(raw, dict):
        for k in CASE_ID_KEYS:
            if k in raw and raw[k]:
                out["case_id"] = str(raw[k])
                break
    if not out["case_id"]:
        out["case_id"] = "unknown_case"
        out["uncertainties"].append("case_id not found under case_id/id/caseId")

    # document list
    key, val = deep_find(raw, DOC_LIST_KEYS)
    if key is not None:
        if isinstance(val, list):
            out["doc_entries"] = val
        elif isinstance(val, dict):
            out["doc_entries"] = list(val.values())
        out["doc_list_key"] = key
    # output contract
    ckey, cval = deep_find(raw, CONTRACT_KEYS)
    if ckey is not None:
        out["output_contract"] = cval
        out["contract_key"] = ckey
    else:
        out["uncertainties"].append(
            "no output_contract/contract/output_fields/required_fields found")
    return out


def looks_like_metadata_snapshot(obj):
    """True if a dict looks like a Crossref/EuropePMC style record."""
    if not isinstance(obj, dict):
        return False
    has_title = bool(obj.get("title"))
    abs_keys = ["abstract", "abstractText", "abstract_text", "description"]
    has_abs = any(obj.get(k) for k in abs_keys)
    has_ids = any(obj.get(k) for k in ("DOI", "doi", "pmid", "pmcid", "issn"))
    return bool(has_title and (has_abs or has_ids))


def extract_abstract(obj):
    for k in ("abstract", "abstractText", "abstract_text", "description"):
        v = obj.get(k)
        if isinstance(v, str) and v.strip():
            # strip simple XML tags from JATS abstracts
            return re.sub(r"<[^>]+>", " ", v).strip()
    return ""


def extract_title(obj):
    t = obj.get("title")
    if isinstance(t, list) and t:
        t = t[0]
    return str(t or "").strip()


def load_pages(workdir, doc_id):
    """Load pages/<doc_id>.jsonl -> list of {page, text}."""
    return read_jsonl(os.path.join(workdir, "pages", doc_id + ".jsonl"))


def valid_judgment(j):
    return j in JUDGMENT_LEVELS
