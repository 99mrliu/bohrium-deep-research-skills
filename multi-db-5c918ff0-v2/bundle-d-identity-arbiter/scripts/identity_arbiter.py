#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
identity_arbiter.py — 论文身份去重判定与确定性合并（paper-identity dedup adjudication & deterministic merge）.

Pipeline:
  STEP 0  write result.json skeleton (status=partial) BEFORE reading any input.
  STEP 1  intake & sniff-classify discovered materials
          (crossref / europepmc / publisher JSON array or JSONL / reference_graph /
           import_state / unknown-quarantined).
  STEP 2  normalize records (identifiers, titles, author surnames; missing vs
          unknown vs not_provided field status).
  STEP 3  tiered pairwise matching: T1 identifier-exact, T2 bibliographic-exact,
          T3 fuzzy candidates -> arbitration queue only (never auto-merged).
  STEP 4  explainable decision log (one JSONL line per evaluated pair).
  STEP 5  deterministic per-field merge with source priority, provenance and
          conflict records.
  STEP 6  identity_report.md + result.json honoring the case output_contract.

Stdlib only. No network, no randomness, no wall-clock in artifacts.
Exit codes: 0 ok | 2 honest degradation (partial) | 3 invalid input.
"""

import argparse
import html
import json
import os
import re
import sys
import unicodedata
from itertools import combinations

VERSION = "1.0.0"

DEFAULT_PRIORITY = ["publisher", "crossref", "europepmc"]

CANONICAL_FIELDS = [
    "doi", "pmid", "pmcid", "title", "year", "authors",
    "journal", "volume", "issue", "pages", "abstract", "url",
]

# reason codes (enumerated in references/matching-rules.md)
RC_SHARED_DOI = "T1_SHARED_DOI"
RC_SHARED_PMID = "T1_SHARED_PMID"
RC_ALIAS_LINK = "T1_ALIAS_LINK"
RC_BIBLIO_EXACT = "T2_BIBLIOGRAPHIC_EXACT"
RC_FUZZY = "T3_FUZZY_CANDIDATE"
RC_ADJ_MERGE = "T3_ADJUDICATED_MERGE"
RC_ADJ_SEPARATE = "T3_ADJUDICATED_SEPARATE"
RC_NO_MATCH = "NO_MATCH"

NOT_PROVIDED_TOKENS = {"not_provided", "not provided", "n/a", "na", "none provided"}


class InvalidInput(Exception):
    """Raised for structurally invalid mandatory input (exit 3)."""


# ---------------------------------------------------------------------------
# normalization helpers
# ---------------------------------------------------------------------------

def norm_doi(value):
    if not isinstance(value, str):
        return None
    v = value.strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/",
                   "https://dx.doi.org/", "http://dx.doi.org/", "doi:"):
        if v.startswith(prefix):
            v = v[len(prefix):]
    v = v.strip().rstrip(".,;:")
    return v or None


def norm_title(value):
    if not isinstance(value, str):
        return None
    v = unicodedata.normalize("NFC", value)
    v = html.unescape(v)
    v = strip_html(v)
    v = v.lower()
    v = re.sub(r"[^\w\s]", " ", v, flags=re.UNICODE)
    v = re.sub(r"\s+", " ", v).strip()
    return v or None


def strip_html(value):
    if not isinstance(value, str):
        return value
    v = re.sub(r"<[^>]+>", " ", value)
    v = html.unescape(v)
    v = re.sub(r"\s+", " ", v).strip()
    return v


def norm_surname(value):
    if not isinstance(value, str):
        return None
    v = unicodedata.normalize("NFC", value).lower()
    v = re.sub(r"[^\w\s-]", "", v, flags=re.UNICODE)
    v = re.sub(r"\s+", " ", v).strip()
    return v or None


def token_set(norm):
    if not norm:
        return frozenset()
    return frozenset(norm.split())


def jaccard(a, b):
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def surname_overlap(a, b):
    """|intersection| / min(|a|, |b|); 0.0 when either side is empty."""
    if not a or not b:
        return 0.0
    return len(set(a) & set(b)) / max(1, min(len(set(a)), len(set(b))))


def field_status(raw, key):
    """missing (key absent) vs unknown (present but null/empty) vs not_provided."""
    if key not in raw:
        return "missing", None
    val = raw.get(key)
    if val is None or val == "" or val == []:
        return "unknown", None
    if isinstance(val, str) and val.strip().lower() in NOT_PROVIDED_TOKENS:
        return "not_provided", None
    return "present", val


# ---------------------------------------------------------------------------
# intake & sniff classification
# ---------------------------------------------------------------------------

def sniff_and_load(path):
    """Return (classification, payload). classification in:
    crossref | europepmc | publisher_array | publisher_jsonl |
    reference_graph | import_state | unknown"""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
    except (OSError, UnicodeDecodeError):
        return "unknown", None
    stripped = text.strip()
    if not stripped:
        return "unknown", None
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        # try JSONL
        rows = []
        ok = True
        for line in stripped.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                ok = False
                break
        if ok and rows and all(isinstance(r, dict) for r in rows):
            return "publisher_jsonl", rows
        return "unknown", None

    if isinstance(data, dict):
        msg = data.get("message")
        if isinstance(msg, dict) and isinstance(msg.get("items"), list):
            return "crossref", data
        rl = data.get("resultList")
        if isinstance(rl, dict) and isinstance(rl.get("result"), list):
            return "europepmc", data
        if isinstance(data.get("aliases"), list) or (
            isinstance(data.get("nodes"), list) and isinstance(data.get("edges"), list)
        ):
            return "reference_graph", data
        if any(k in data for k in ("import_state", "imported_ids", "imported",
                                   "last_import", "cursor", "seen")):
            return "import_state", data
        return "unknown", None
    if isinstance(data, list) and all(isinstance(x, dict) for x in data):
        return "publisher_array", data
    return "unknown", None


# ---------------------------------------------------------------------------
# record extraction
# ---------------------------------------------------------------------------

def _year_from_dateparts(item):
    for key in ("issued", "published-print", "published-online", "published", "created"):
        dp = item.get(key)
        if isinstance(dp, dict):
            parts = dp.get("date-parts")
            if isinstance(parts, list) and parts and isinstance(parts[0], list) and parts[0]:
                y = parts[0][0]
                if isinstance(y, int):
                    return y
                if isinstance(y, str) and y.isdigit():
                    return int(y)
    return None


def _crossref_authors(item):
    authors, surnames = [], []
    raw = item.get("author")
    if isinstance(raw, list):
        for a in raw:
            if isinstance(a, dict):
                fam = a.get("family") or ""
                giv = a.get("given") or ""
                name = (giv + " " + fam).strip() or a.get("name") or ""
                if name:
                    authors.append(name)
                s = norm_surname(fam or name.split()[-1] if name else fam)
                if s:
                    surnames.append(s)
            elif isinstance(a, str):
                authors.append(a)
                s = norm_surname(a.split()[-1])
                if s:
                    surnames.append(s)
    return authors, surnames


def _authorstring_names(value):
    """EuropePMC authorString 'Zhang W, Li N.' -> display names + surnames."""
    authors, surnames = [], []
    if not isinstance(value, str):
        return authors, surnames
    for chunk in value.rstrip(".").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        authors.append(chunk)
        s = norm_surname(chunk.split()[0])
        if s:
            surnames.append(s)
    return authors, surnames


def _publisher_authors(item):
    authors, surnames = [], []
    raw = item.get("authors", item.get("author"))
    if isinstance(raw, str):
        raw, _ = _authorstring_names(raw)
    if isinstance(raw, list):
        for a in raw:
            if isinstance(a, dict):
                fam = a.get("family") or a.get("surname") or ""
                giv = a.get("given") or a.get("forename") or ""
                name = (giv + " " + fam).strip() or a.get("name") or ""
                if name:
                    authors.append(name)
                s = norm_surname(fam or (name.split()[-1] if name else ""))
                if s:
                    surnames.append(s)
            elif isinstance(a, str):
                authors.append(a)
                if "," in a:  # "Family, Given"
                    s = norm_surname(a.split(",", 1)[0])
                else:  # "Given Family"
                    s = norm_surname(a.split()[-1])
                if s:
                    surnames.append(s)
    return authors, surnames


def _publisher_year(item):
    for key in ("year", "pubYear", "publication_year"):
        v = item.get(key)
        if isinstance(v, int):
            return v
        if isinstance(v, str) and v.strip().isdigit():
            return int(v.strip())
    for key in ("published", "date", "publication_date", "published_date"):
        v = item.get(key)
        if isinstance(v, str):
            m = re.match(r"\s*(\d{4})", v)
            if m:
                return int(m.group(1))
        if isinstance(v, dict):
            return _year_from_dateparts({"issued": v})
    return None


def extract_records(classification, payload, artifact_id):
    """Normalize raw payload into common records."""
    records = []

    def base(db, locator):
        return {
            "id": None, "db": db, "artifact_id": artifact_id, "locator": locator,
            "doi": None, "pmid": None, "pmcid": None, "title": None,
            "title_norm": None, "year": None, "authors": [], "surnames": [],
            "journal": None, "volume": None, "issue": None, "pages": None,
            "abstract": None, "url": None, "field_status": {},
        }

    if classification == "crossref":
        for i, item in enumerate(payload.get("message", {}).get("items", [])):
            if not isinstance(item, dict):
                continue
            rec = base("crossref", "message.items[%d]" % i)
            _, doi = field_status(item, "DOI")
            rec["doi"] = norm_doi(doi)
            _, ttl = field_status(item, "title")
            if isinstance(ttl, list) and ttl:
                ttl = ttl[0]
            rec["title"] = strip_html(ttl) if isinstance(ttl, str) else None
            rec["title_norm"] = norm_title(ttl)
            rec["year"] = _year_from_dateparts(item)
            rec["authors"], rec["surnames"] = _crossref_authors(item)
            _, ct = field_status(item, "container-title")
            rec["journal"] = ct[0] if isinstance(ct, list) and ct else (ct if isinstance(ct, str) else None)
            for k_src, k_dst in (("volume", "volume"), ("issue", "issue"),
                                 ("page", "pages"), ("URL", "url")):
                st, v = field_status(item, k_src)
                rec["field_status"][k_dst] = st
                if isinstance(v, (str, int)):
                    rec[k_dst] = str(v)
            st, ab = field_status(item, "abstract")
            rec["field_status"]["abstract"] = st
            rec["abstract"] = strip_html(ab) if isinstance(ab, str) else None
            for key in ("DOI", "title", "author", "issued"):
                rec["field_status"].setdefault(key.lower(), field_status(item, key)[0])
            records.append(rec)

    elif classification == "europepmc":
        for i, item in enumerate(payload.get("resultList", {}).get("result", [])):
            if not isinstance(item, dict):
                continue
            rec = base("europepmc", "resultList.result[%d]" % i)
            for k in ("pmid", "pmcid"):
                st, v = field_status(item, k)
                rec["field_status"][k] = st
                rec[k] = str(v).strip() if isinstance(v, (str, int)) and str(v).strip() else None
            _, doi = field_status(item, "doi")
            rec["doi"] = norm_doi(doi)
            st, ttl = field_status(item, "title")
            rec["field_status"]["title"] = st
            rec["title"] = strip_html(ttl) if isinstance(ttl, str) else None
            rec["title_norm"] = norm_title(ttl)
            st, py = field_status(item, "pubYear")
            rec["field_status"]["pubYear"] = st
            if isinstance(py, str) and py.strip().isdigit():
                rec["year"] = int(py.strip())
            elif isinstance(py, int):
                rec["year"] = py
            rec["authors"], rec["surnames"] = _authorstring_names(item.get("authorString"))
            st, jt = field_status(item, "journalTitle")
            if st == "missing":
                jinfo = item.get("journalInfo")
                if isinstance(jinfo, dict):
                    j = jinfo.get("journal")
                    if isinstance(j, dict):
                        jt = j.get("title")
                        st = "present" if jt else "unknown"
            rec["field_status"]["journal"] = st
            rec["journal"] = jt if isinstance(jt, str) else None
            st, ab = field_status(item, "abstractText")
            rec["field_status"]["abstract"] = st
            rec["abstract"] = strip_html(ab) if isinstance(ab, str) else None
            records.append(rec)

    elif classification in ("publisher_array", "publisher_jsonl"):
        for i, item in enumerate(payload):
            if not isinstance(item, dict):
                continue
            locator = ("line %d" % (i + 1)) if classification == "publisher_jsonl" else ("[%d]" % i)
            rec = base("publisher", locator)
            st, v = field_status(item, "doi")
            if st == "missing":
                st, v = field_status(item, "DOI")
            rec["field_status"]["doi"] = st
            rec["doi"] = norm_doi(v)
            for k in ("pmid", "pmcid"):
                st, v = field_status(item, k)
                rec["field_status"][k] = st
                rec[k] = str(v).strip() if isinstance(v, (str, int)) and str(v).strip() else None
            st, ttl = field_status(item, "title")
            rec["field_status"]["title"] = st
            rec["title"] = strip_html(ttl) if isinstance(ttl, str) else None
            rec["title_norm"] = norm_title(ttl)
            rec["year"] = _publisher_year(item)
            rec["authors"], rec["surnames"] = _publisher_authors(item)
            for k in ("journal", "volume", "issue", "pages", "page", "url", "URL"):
                st, v = field_status(item, k)
                dst = {"page": "pages", "URL": "url"}.get(k, k)
                if dst in rec["field_status"] and rec["field_status"][dst] == "present":
                    continue
                rec["field_status"][dst] = st
                if isinstance(v, (str, int)):
                    rec[dst] = str(v)
            st, ab = field_status(item, "abstract")
            rec["field_status"]["abstract"] = st
            rec["abstract"] = strip_html(ab) if isinstance(ab, str) else None
            records.append(rec)

    return records


def extract_alias_pairs(payloads):
    """Explicit cross-identifier alias pairs from reference_graph / import_state.
    NEVER invent pmid<->doi mappings; only declared pairs are honored."""
    pairs = set()

    def add(a_kind, a_val, b_kind, b_val):
        ka = norm_doi(a_val) if a_kind == "doi" else (str(a_val).strip() if a_val else None)
        kb = norm_doi(b_val) if b_kind == "doi" else (str(b_val).strip() if b_val else None)
        if ka and kb and ka != kb:
            pairs.add(frozenset(((a_kind, ka), (b_kind, kb))))

    kinds = ("doi", "pmid", "pmcid")
    for payload in payloads:
        entries = []
        if isinstance(payload, dict):
            if isinstance(payload.get("aliases"), list):
                entries = payload["aliases"]
            elif isinstance(payload.get("known_aliases"), list):
                entries = payload["known_aliases"]
        for e in entries:
            if not isinstance(e, dict):
                continue
            present = [(k, e[k]) for k in kinds if e.get(k)]
            for (ka, va), (kb, vb) in combinations(present, 2):
                add(ka, va, kb, vb)
    return pairs


# ---------------------------------------------------------------------------
# tiered matching
# ---------------------------------------------------------------------------

def evaluate_pair(a, b, alias_pairs):
    shared = []
    if a["doi"] and b["doi"] and a["doi"] == b["doi"]:
        shared.append("doi:%s" % a["doi"])
    if a["pmid"] and b["pmid"] and a["pmid"] == b["pmid"]:
        shared.append("pmid:%s" % a["pmid"])
    if a["pmcid"] and b["pmcid"] and a["pmcid"] == b["pmcid"]:
        shared.append("pmcid:%s" % a["pmcid"])

    alias_hit = None
    ids_a = {(k, a[k]) for k in ("doi", "pmid", "pmcid") if a[k]}
    ids_b = {(k, b[k]) for k in ("doi", "pmid", "pmcid") if b[k]}
    for ia in sorted(ids_a):
        for ib in sorted(ids_b):
            if ia[0] != ib[0] and frozenset((ia, ib)) in alias_pairs:
                alias_hit = "%s:%s~%s:%s" % (ia[0], ia[1], ib[0], ib[1])
    if alias_hit:
        shared.append("alias:" + alias_hit)

    t_sim = round(jaccard(token_set(a["title_norm"]), token_set(b["title_norm"])), 4)
    s_ov = round(surname_overlap(a["surnames"], b["surnames"]), 4)
    if a["year"] is not None and b["year"] is not None:
        y_diff = abs(a["year"] - b["year"])
    else:
        y_diff = None

    evidence = {
        "shared_identifiers": shared,
        "title_sim": t_sim,
        "surname_overlap": s_ov,
        "year_diff": y_diff,
    }

    if any(s.startswith("doi:") for s in shared):
        return "T1", "merge", RC_SHARED_DOI, evidence
    if any(s.startswith("pmid:") for s in shared) or any(s.startswith("pmcid:") for s in shared):
        return "T1", "merge", RC_SHARED_PMID, evidence
    if alias_hit:
        return "T1", "merge", RC_ALIAS_LINK, evidence
    if (a["title_norm"] and a["title_norm"] == b["title_norm"]
            and a["year"] is not None and a["year"] == b["year"]
            and a["surnames"] and b["surnames"] and a["surnames"][0] == b["surnames"][0]):
        return "T2", "merge", RC_BIBLIO_EXACT, evidence
    if t_sim >= 0.6 and s_ov >= 0.5 and y_diff is not None and y_diff <= 1:
        return "T3", "pending_arbitration", RC_FUZZY, evidence
    return "NONE", "separate", RC_NO_MATCH, evidence


# ---------------------------------------------------------------------------
# deterministic merge
# ---------------------------------------------------------------------------

def load_priority_table(script_dir):
    """Optional per-field source priority overrides from references/merge-policy.md
    (fenced ```priority-json block). Falls back to DEFAULT_PRIORITY."""
    table = {"default": list(DEFAULT_PRIORITY)}
    path = os.path.join(script_dir, os.pardir, "references", "merge-policy.md")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return table
    m = re.search(r"```priority-json\s*(\{.*?\})\s*```", text, re.DOTALL)
    if not m:
        return table
    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError:
        return table
    if isinstance(data, dict):
        for key, val in data.items():
            if isinstance(val, list) and all(isinstance(x, str) for x in val) and val:
                table[key] = val
    return table


def merge_components(records, edges, priority_table):
    """Union-find over merge edges; deterministic per-field merge."""
    parent = {r["id"]: r["id"] for r in records}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x, y):
        rx, ry = find(x), find(y)
        if rx != ry:
            parent[max(rx, ry)] = min(rx, ry)

    tier_by_edge = {}
    for (ia, ib, tier, _reason) in edges:
        union(ia, ib)
        tier_by_edge.setdefault(frozenset((ia, ib)), tier)

    groups = {}
    for r in records:
        groups.setdefault(find(r["id"]), []).append(r)

    canonical = []
    conflicts = []
    for root in sorted(groups):
        members = sorted(groups[root], key=lambda r: r["id"])
        member_ids = [m["id"] for m in members]
        comp_tiers = [tier_by_edge[fs] for fs in tier_by_edge
                      if all(x in member_ids for x in fs)]
        merge_tier = "T1"
        if comp_tiers:
            merge_tier = sorted(comp_tiers)[0]
        canon = {"canonical_id": None, "member_records": member_ids,
                 "merge_tier": "single" if len(members) == 1 else merge_tier,
                 "provenance": {}}
        for field in CANONICAL_FIELDS:
            prio = priority_table.get(field, priority_table["default"])
            candidates = []
            for m in members:
                val = m.get(field)
                if val is None or val == [] or val == "":
                    continue
                rank = prio.index(m["db"]) if m["db"] in prio else len(prio)
                candidates.append((rank, m["id"], val,
                                   {"db": m["db"], "artifact_id": m["artifact_id"],
                                    "locator": m["locator"]}))
            if not candidates:
                canon[field] = None
                canon["provenance"][field] = None
                continue
            candidates.sort(key=lambda c: (c[0], c[1]))
            chosen = candidates[0]
            canon[field] = chosen[2]
            canon["provenance"][field] = chosen[3]
            distinct = {}
            for rank, rid, val, prov in candidates:
                key = json.dumps(val, sort_keys=True, ensure_ascii=False)
                distinct.setdefault(key, (val, prov))
            if len(distinct) > 1:
                conflicts.append({
                    "canonical_members": member_ids,
                    "field": field,
                    "values": [
                        {"db": prov["db"], "artifact_id": prov["artifact_id"],
                         "locator": prov["locator"], "value": val}
                        for val, prov in sorted(distinct.values(),
                                                key=lambda vp: (vp[1]["db"], vp[1]["locator"]))
                    ],
                    "chosen": {"db": chosen[3]["db"], "value": chosen[2]},
                    "rule": "source_priority:%s" % ">".join(prio),
                })
        canonical.append(canon)

    canonical.sort(key=lambda c: (0, c["doi"]) if c["doi"]
                   else (1, norm_title(c["title"]) or ""))
    for i, c in enumerate(canonical, 1):
        c["canonical_id"] = "canon-%04d" % i
    conflicts.sort(key=lambda c: (c["canonical_members"][0], c["field"]))
    return canonical, conflicts


# ---------------------------------------------------------------------------
# output_contract handling
# ---------------------------------------------------------------------------

def parse_contract(raw):
    """Normalize output_contract shapes: dict{name:spec|str} | list[name|dict] | str."""
    fields = {}
    if isinstance(raw, dict):
        for name, spec in raw.items():
            if isinstance(spec, dict):
                fields[str(name)] = str(spec.get("type", "")).lower()
            elif isinstance(spec, str):
                fields[str(name)] = spec.lower() if spec.lower() in ("dict", "list", "string") else ""
            else:
                fields[str(name)] = ""
    elif isinstance(raw, list):
        for entry in raw:
            if isinstance(entry, str):
                fields[entry] = ""
            elif isinstance(entry, dict) and entry.get("name"):
                fields[str(entry["name"])] = str(entry.get("type", "")).lower()
    elif isinstance(raw, str) and raw.strip():
        fields[raw.strip()] = ""
    return fields


def fill_contract(fields, ctx):
    """Fill contract fields by name heuristics; never fabricate."""
    out, unresolved = {}, []
    for name in sorted(fields):
        lname = name.lower()
        want = fields[name]
        value, vtype = None, None
        if "canonical" in lname or "merged" in lname or (
                "record" in lname and "decision" not in lname and "change" not in lname):
            value, vtype = ctx["canonical"], "list"
        elif "conflict" in lname:
            value, vtype = ctx["conflicts"], "list"
        elif "arbitration" in lname or "pending" in lname:
            value, vtype = ctx["arbitration"], "list"
        elif "decision" in lname or "trace" in lname:
            value, vtype = ctx["decisions"], "list"
        elif "summary" in lname or "statistic" in lname or "count" in lname:
            value, vtype = ctx["summary"], "dict"
        elif "report" in lname:
            value, vtype = ctx["report_path"], "string"
        if value is None:
            unresolved.append(name)
            out[name] = None
            continue
        type_ok = {"list": list, "dict": dict, "string": str}
        if want in type_ok and not isinstance(value, type_ok[want]):
            unresolved.append(name)
            out[name] = None
            continue
        out[name] = value
    return out, unresolved


# ---------------------------------------------------------------------------
# main pipeline
# ---------------------------------------------------------------------------

def parse_args(argv=None):
    p = argparse.ArgumentParser(
        prog="identity_arbiter.py",
        description="论文身份去重判定与确定性合并：分层匹配 + 仲裁队列 + 字段级溯源合并。")
    p.add_argument("--case", default="/input/case.json", help="case.json 路径")
    p.add_argument("--task", default="/input/task.md", help="task.md 路径")
    p.add_argument("--work", default="/app/work", help="工作产物目录")
    p.add_argument("--out", default="/app/output", help="result.json 输出目录")
    p.add_argument("--adjudications", default=None,
                   help="可选 JSON：[{\"pair\":[idA,idB],\"decision\":\"merge|separate\",\"rationale\":\"...\"}]")
    return p.parse_args(argv)


def write_json(path, obj):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")


def main(argv=None):
    args = parse_args(argv)
    os.makedirs(args.work, exist_ok=True)
    os.makedirs(args.out, exist_ok=True)
    result_path = os.path.join(args.out, "result.json")

    # ---- STEP 0: skeleton BEFORE reading inputs ---------------------------
    skeleton = {
        "case_id": None,
        "status": "partial",
        "sources": [],
        "uncertainty": ["pipeline started; result.json skeleton written before reading inputs"],
        "change_records": ["step0: wrote result.json skeleton (status=partial)"],
        "artifacts": {},
        "unresolved_contract_fields": [],
    }
    write_json(result_path, skeleton)

    try:
        run(args, result_path)
    except InvalidInput as exc:
        skeleton["status"] = "error"
        skeleton["uncertainty"] = ["invalid input: %s" % exc]
        skeleton["change_records"].append("abort: invalid input (%s)" % exc)
        write_json(result_path, skeleton)
        return 3
    except Exception as exc:  # honest partial, never crash
        skeleton["status"] = "partial"
        skeleton["uncertainty"] = ["unexpected failure: %s: %s" % (type(exc).__name__, exc)]
        skeleton["change_records"].append("abort: unexpected failure %s" % type(exc).__name__)
        write_json(result_path, skeleton)
        return 2

    with open(result_path, "r", encoding="utf-8") as fh:
        final = json.load(fh)
    return {"ok": 0, "partial": 2, "error": 3}.get(final.get("status"), 2)


def run(args, result_path):
    change_records = ["step0: wrote result.json skeleton (status=partial)"]
    uncertainty = []

    # ---- read case ---------------------------------------------------------
    if not os.path.isfile(args.case):
        raise InvalidInput("case file not found: %s" % args.case)
    try:
        with open(args.case, "r", encoding="utf-8") as fh:
            case = json.load(fh)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise InvalidInput("case.json is not valid JSON: %s" % exc)
    if not isinstance(case, dict):
        raise InvalidInput("case.json top level must be an object")
    case_id = case.get("case_id")
    if not case_id:
        raise InvalidInput("case.json missing case_id")
    case_dir = os.path.dirname(os.path.abspath(args.case))
    change_records.append("intake: loaded case.json (case_id=%s)" % case_id)

    if os.path.isfile(args.task):
        change_records.append("intake: task.md present (%s)" % args.task)
    else:
        uncertainty.append("task.md not found at %s" % args.task)

    # ---- discover materials -------------------------------------------------
    material_paths = []
    raw_mats = case.get("materials", [])
    if isinstance(raw_mats, dict):
        raw_mats = list(raw_mats.values())
    if isinstance(raw_mats, list):
        for m in raw_mats:
            p = m.get("path") if isinstance(m, dict) else m
            if isinstance(p, str):
                material_paths.append(p if os.path.isabs(p) else os.path.join(case_dir, p))
    mats_dir = os.path.join(case_dir, "materials")
    if os.path.isdir(mats_dir):
        for name in sorted(os.listdir(mats_dir)):
            fp = os.path.join(mats_dir, name)
            if os.path.isfile(fp):
                material_paths.append(fp)
    material_paths = sorted(set(material_paths))

    # ---- intake & sniff ------------------------------------------------------
    sources, records, alias_payloads, quarantined = [], [], [], []
    for path in material_paths:
        name = os.path.basename(path)
        if name in ("case.json", "task.md") or name.startswith("adjudications"):
            continue
        cls, payload = sniff_and_load(path)
        if cls == "unknown":
            quarantined.append({"file": name, "reason": "unrecognized shape; quarantined, not parsed"})
            sources.append({"file": name, "classification": "unknown", "records": 0})
            continue
        if cls in ("reference_graph", "import_state"):
            alias_payloads.append(payload)
            sources.append({"file": name, "classification": cls, "records": 0})
            continue
        recs = extract_records(cls, payload, name)
        sources.append({"file": name, "classification": cls, "records": len(recs)})
        records.extend(recs)
    records.sort(key=lambda r: (r["artifact_id"], r["locator"]))
    for i, r in enumerate(records, 1):
        r["id"] = "rec-%04d" % i
    change_records.append("intake: classified %d material file(s); %d record(s); %d quarantined"
                          % (len(sources), len(records), len(quarantined)))
    if quarantined:
        uncertainty.append("%d material file(s) quarantined as unknown shape: %s"
                           % (len(quarantined), ", ".join(q["file"] for q in quarantined)))

    alias_pairs = extract_alias_pairs(alias_payloads)
    change_records.append("intake: %d explicit alias pair(s) from reference_graph/import_state"
                          % len(alias_pairs))

    # ---- adjudications -------------------------------------------------------
    adjudications = {}
    if args.adjudications:
        if not os.path.isfile(args.adjudications):
            raise InvalidInput("adjudications file not found: %s" % args.adjudications)
        try:
            with open(args.adjudications, "r", encoding="utf-8") as fh:
                raw_adj = json.load(fh)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise InvalidInput("adjudications file is not valid JSON: %s" % exc)
        if not isinstance(raw_adj, list):
            raise InvalidInput("adjudications must be a JSON array")
        for entry in raw_adj:
            if not isinstance(entry, dict):
                continue
            pair = entry.get("pair")
            dec = entry.get("decision")
            if isinstance(pair, list) and len(pair) == 2 and dec in ("merge", "separate"):
                adjudications[frozenset((str(pair[0]), str(pair[1])))] = {
                    "decision": dec, "rationale": entry.get("rationale", "")}
        change_records.append("adjudication: loaded %d ruling(s) from %s"
                              % (len(adjudications), args.adjudications))

    # ---- pairwise evaluation --------------------------------------------------
    decisions, edges, arbitration = [], [], []
    tier_counts = {"T1": 0, "T2": 0, "T3": 0, "NONE": 0}
    for a, b in combinations(records, 2):
        tier, decision, reason, evidence = evaluate_pair(a, b, alias_pairs)
        adj = adjudications.get(frozenset((a["id"], b["id"])))
        if tier == "T3" and adj:
            if adj["decision"] == "merge":
                tier, decision, reason = "T3", "merge", RC_ADJ_MERGE
            else:
                decision, reason = "separate", RC_ADJ_SEPARATE
            evidence["adjudication_rationale"] = adj["rationale"]
        tier_counts[tier] += 1
        line = {"pair": [a["id"], b["id"]], "tier": tier, "decision": decision,
                "reason_code": reason, "evidence": evidence}
        decisions.append(line)
        if decision == "merge":
            edges.append((a["id"], b["id"], tier, reason))
        elif tier == "T3" and decision == "pending_arbitration":
            arbitration.append({"pair": [a["id"], b["id"]], "tier": "T3",
                                "status": "pending_arbitration",
                                "reason_code": reason, "evidence": evidence})
    change_records.append("matching: evaluated %d pair(s): T1=%d T2=%d T3=%d NONE=%d"
                          % (len(decisions), tier_counts["T1"], tier_counts["T2"],
                             tier_counts["T3"], tier_counts["NONE"]))

    # ---- merge ------------------------------------------------------------------
    script_dir = os.path.dirname(os.path.abspath(__file__))
    priority_table = load_priority_table(script_dir)
    canonical, conflicts = merge_components(records, edges, priority_table)
    n_merged = len(records) - len(canonical)
    change_records.append("merge: %d record(s) -> %d canonical record(s); %d field conflict(s)"
                          % (len(records), len(canonical), len(conflicts)))
    if arbitration:
        uncertainty.append("%d T3 fuzzy pair(s) pending arbitration (NOT merged): %s"
                           % (len(arbitration),
                              "; ".join("%s~%s" % (q["pair"][0], q["pair"][1]) for q in arbitration)))

    # ---- artifacts ---------------------------------------------------------------
    decisions_path = os.path.join(args.work, "dedup_decisions.jsonl")
    with open(decisions_path, "w", encoding="utf-8") as fh:
        for d in decisions:
            fh.write(json.dumps(d, ensure_ascii=False, sort_keys=True) + "\n")
    merged_path = os.path.join(args.work, "merged_records.json")
    write_json(merged_path, canonical)
    queue_path = os.path.join(args.work, "arbitration_queue.json")
    write_json(queue_path, arbitration)
    conflict_path = os.path.join(args.work, "conflict_log.json")
    write_json(conflict_path, conflicts)
    report_path = os.path.join(args.work, "identity_report.md")
    with open(report_path, "w", encoding="utf-8") as fh:
        fh.write(render_report(case_id, sources, quarantined, tier_counts,
                               len(records), canonical, arbitration, conflicts,
                               len(alias_pairs), bool(args.adjudications)))
    change_records.append("output: wrote dedup_decisions.jsonl, merged_records.json, "
                          "arbitration_queue.json, conflict_log.json, identity_report.md")

    artifacts = {
        "merged_records": merged_path,
        "dedup_decisions": decisions_path,
        "arbitration_queue": queue_path,
        "conflict_log": conflict_path,
        "identity_report": report_path,
    }

    # ---- status -------------------------------------------------------------------
    degraded = bool(arbitration) or bool(quarantined)
    status = "partial" if degraded else "ok"
    if n_merged == 0 and not records:
        status = "partial"
        uncertainty.append("no bibliographic records were extracted from any material")

    # ---- result.json ----------------------------------------------------------------
    summary = {
        "input_records": len(records),
        "canonical_records": len(canonical),
        "merges_applied": n_merged,
        "tier_counts": tier_counts,
        "arbitration_pending": len(arbitration),
        "conflicts": len(conflicts),
        "quarantined_files": len(quarantined),
        "alias_pairs_loaded": len(alias_pairs),
    }
    ctx = {"canonical": canonical, "conflicts": conflicts, "arbitration": arbitration,
           "decisions": decisions, "summary": summary, "report_path": report_path}
    contract_fields = parse_contract(case.get("output_contract"))
    contract_out, unresolved = fill_contract(contract_fields, ctx)

    result = dict(contract_out)
    result.update({
        "case_id": case_id,
        "status": status,
        "sources": sources,
        "uncertainty": uncertainty,
        "change_records": change_records,
        "artifacts": artifacts,
        "summary": summary,
        "unresolved_contract_fields": unresolved,
        "quarantined_materials": quarantined,
    })
    write_json(result_path, result)


def render_report(case_id, sources, quarantined, tier_counts, n_records,
                  canonical, arbitration, conflicts, n_aliases, had_adjudications):
    lines = []
    lines.append("# Identity Dedup Report — %s" % case_id)
    lines.append("")
    lines.append("## 数据源分类 (sources)")
    lines.append("")
    lines.append("| file | classification | records |")
    lines.append("|---|---|---|")
    for s in sources:
        lines.append("| %s | %s | %d |" % (s["file"], s["classification"], s["records"]))
    lines.append("")
    if quarantined:
        lines.append("## 隔离区 (quarantined, unknown shape)")
        lines.append("")
        for q in quarantined:
            lines.append("- `%s`: %s" % (q["file"], q["reason"]))
        lines.append("")
    lines.append("## 分层匹配统计 (tier counts)")
    lines.append("")
    lines.append("- 输入记录: %d；显式别名对: %d；裁决文件: %s"
                 % (n_records, n_aliases, "yes" if had_adjudications else "no"))
    lines.append("- T1 identifier-exact 对: %d" % tier_counts["T1"])
    lines.append("- T2 bibliographic-exact 对: %d" % tier_counts["T2"])
    lines.append("- T3 fuzzy candidate 对: %d" % tier_counts["T3"])
    lines.append("- 无匹配对: %d" % tier_counts["NONE"])
    lines.append("- 规范记录数: %d" % len(canonical))
    lines.append("")
    lines.append("## 待仲裁队列 (arbitration pending)")
    lines.append("")
    if arbitration:
        for q in arbitration:
            ev = q["evidence"]
            lines.append("- `%s` ~ `%s`: title_sim=%.4f, surname_overlap=%.4f, year_diff=%s — **pending, NOT merged**"
                         % (q["pair"][0], q["pair"][1], ev["title_sim"],
                            ev["surname_overlap"], str(ev["year_diff"])))
    else:
        lines.append("（无）")
    lines.append("")
    lines.append("## 字段冲突摘要 (conflicts)")
    lines.append("")
    if conflicts:
        lines.append("| canonical members | field | chosen db | rule |")
        lines.append("|---|---|---|---|")
        for c in conflicts:
            lines.append("| %s | %s | %s | %s |"
                         % ("/".join(c["canonical_members"]), c["field"],
                            c["chosen"]["db"], c["rule"]))
    else:
        lines.append("（无）")
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())
