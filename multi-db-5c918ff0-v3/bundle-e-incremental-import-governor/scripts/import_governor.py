#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
import_governor.py — 增量导入治理与变更追踪(incremental-import-governor)主引擎。

治理多数据库联合检索的"时间维度":把组织者本地的上一轮 import_state
(逐库水印/游标 + 逐记录内容哈希,可有三种方言)与当前离线响应材料对账,
产出六路分类(new / unchanged / changed / withdrawn /
unverifiable_withdrawal / inconsistent_state)、带 field 级 before→after 的
变更证据、水印推进提案(requires_approval,绝不静默写回)与差异报告。

硬约束:Python 3 标准库;离线;确定性(同一输入→字节级一致);产物中无墙钟、
无随机数、无绝对路径。退出码:0 = success;2 = 诚实降级 partial;3 = input_error。
"""
import argparse
import csv
import hashlib
import io
import json
import os
import re
import shutil
import sys
import tempfile
import unicodedata

SKILL_NAME = "incremental-import-governor"
TOOL_NAME = "import_governor.py"
VERSION = "1.0.0"

FINGERPRINT_FIELDS = ["title", "authors", "year", "venue", "doi", "pmid"]
CLASSES = ["new", "unchanged", "changed", "withdrawn",
           "unverifiable_withdrawal", "inconsistent_state"]
# 需要模型(或人)给出处置决定的类别
REVIEW_CLASSES = ["changed", "withdrawn", "unverifiable_withdrawal",
                  "inconsistent_state"]
ALLOWED_DISPOSITIONS = {
    "changed": ["accept_change", "keep_previous", "escalate"],
    "withdrawn": ["exclude_withdrawn", "keep_previous", "escalate"],
    "unverifiable_withdrawal": ["keep_previous", "escalate"],
    "inconsistent_state": ["keep_previous", "escalate"],
    "new": ["accept_change"],
    "unchanged": ["accept_change"],
}
DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$")


# ---------------------------------------------------------------------------
# 确定性 IO 与哈希
# ---------------------------------------------------------------------------

def _canon(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_json(obj):
    return sha256_bytes(_canon(obj).encode("utf-8"))


def write_json(path, obj):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True))
        f.write("\n")


def write_text(path, text):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# 文本与标识符规范化(指纹定义的一部分,改动即变更指纹语义)
# ---------------------------------------------------------------------------

def norm_text(s):
    """NFKC 归一 → casefold → 折叠空白;空值归一为 None。"""
    if s is None:
        return None
    s = unicodedata.normalize("NFKC", str(s))
    s = s.casefold()
    s = re.sub(r"\s+", " ", s).strip()
    return s or None


def norm_doi(d):
    if d is None:
        return None
    s = str(d).strip().casefold()
    for p in ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/",
              "http://dx.doi.org/", "doi.org/", "doi:"):
        if s.startswith(p):
            s = s[len(p):]
    s = s.strip().rstrip(".")
    return s or None


def norm_pmid(p):
    if p is None:
        return None
    s = str(p).strip()
    if s.startswith("pmid:"):
        s = s[5:]
    m = re.search(r"\d+", s)
    return m.group(0) if m else None


def norm_year(y):
    if y is None:
        return None
    if isinstance(y, (list, tuple)) and y:
        y = y[0]
    m = re.search(r"(1[5-9]\d{2}|20\d{2}|21\d{2})", str(y))
    return m.group(1) if m else None


def looks_like_doi(ident):
    if not ident:
        return False
    s = str(ident).strip().casefold()
    if s.startswith("doi:"):
        s = s[4:]
    return bool(DOI_RE.match(s))


def fingerprint_fields(fields):
    """内容指纹:对规范化后的 FINGERPRINT_FIELDS 子集做 canonical JSON 的 sha256。

    fields 取值规则:标题/出处 NFKC+casefold+折叠空白;作者保持顺序逐人规范化;
    年份取首个四位年份;DOI 去前缀小写;PMID 取数字串。该函数是"changed 判定"
    的唯一标准,任何修改都必须同步更新 references/import-state-dialects.md。
    """
    fields = fields or {}
    authors = fields.get("authors") or []
    if isinstance(authors, str):
        authors = [a.strip() for a in re.split(r"[;|]", authors) if a.strip()]
    payload = {
        "title": norm_text(fields.get("title")),
        "authors": [norm_text(a) for a in authors],
        "year": norm_year(fields.get("year")),
        "venue": norm_text(fields.get("venue")),
        "doi": norm_doi(fields.get("doi")),
        "pmid": norm_pmid(fields.get("pmid")),
    }
    return sha256_json(payload)


# ---------------------------------------------------------------------------
# 材料嗅探
# ---------------------------------------------------------------------------

def _read_text(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _try_json(text):
    try:
        return json.loads(text)
    except Exception:
        return None


def _try_jsonl(text):
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        obj = _try_json(line)
        if not isinstance(obj, dict):
            return None
        rows.append(obj)
    return rows or None


HASH_KEYS = ("content_hash", "fields_hash", "hash")
IDENT_KEYS = ("identifier", "doi", "pmid", "id")


def _row_has_state_shape(row):
    return (any(k in row for k in HASH_KEYS)
            and any(k in row for k in IDENT_KEYS)
            and "title" not in row)


def detect_import_state_dialect(obj, jsonl_rows):
    """返回 (dialect, reason);无法识别返回 (None, reason)。"""
    if isinstance(obj, dict):
        if isinstance(obj.get("records"), list) and obj.get("records") \
                and all(isinstance(r, dict) for r in obj["records"]):
            return "a", "顶层含 records 数组(可选 watermarks 对象)"
        if obj and all(isinstance(v, dict) for v in obj.values()) \
                and all(any(k in v for k in HASH_KEYS) for v in obj.values()):
            return "b", "扁平映射 {identifier: {hash, source_db}}"
        if "records" in obj and not obj["records"]:
            return "a", "顶层含空 records 数组(空状态,合法)"
    if jsonl_rows is not None and all(_row_has_state_shape(r) for r in jsonl_rows):
        return "c", "JSONL 行,每行含 identifier/doi/pmid 与 content_hash/hash"
    return None, "不符合方言 a(records+watermarks)/b(扁平映射)/c(JSONL) 任一结构"


def sniff_material(path, rel):
    """结构嗅探:返回 {path, role, detail, sha256}。role ∈
    crossref_response / europepmc_response / publisher_records /
    import_state / import_state_unknown / reference_graph / unknown。"""
    rec = {"path": rel, "sha256": sha256_file(path), "role": "unknown",
           "detail": ""}
    name = os.path.basename(path).lower()
    text = _read_text(path)
    obj = _try_json(text)
    jsonl_rows = None if obj is not None else _try_jsonl(text)

    def is_state_hint():
        return ("import_state" in name or "import-state" in name
                or "ingest_state" in name or "state.json" in name)

    if is_state_hint():
        dialect, reason = detect_import_state_dialect(obj, jsonl_rows)
        if dialect:
            rec.update(role="import_state",
                       detail="文件名提示 + 方言 %s:%s" % (dialect, reason))
        else:
            rec.update(role="import_state_unknown",
                       detail="文件名提示为 import_state,但结构嗅探失败:" + reason)
        return rec
    if isinstance(obj, dict):
        msg = obj.get("message")
        if obj.get("message-type") == "work-list" \
                or (isinstance(msg, dict) and isinstance(msg.get("items"), list)):
            rec.update(role="crossref_response",
                       detail="Crossref works 信封(message.items)")
            return rec
        rl = obj.get("resultList")
        if isinstance(rl, dict) and isinstance(rl.get("result"), list):
            rec.update(role="europepmc_response",
                       detail="EuropePMC resultList.result")
            return rec
        if isinstance(obj.get("nodes"), list) and isinstance(obj.get("edges"), list):
            rec.update(role="reference_graph",
                       detail="引用图(nodes/edges),本技能不治理,仅登记")
            return rec
        dialect, reason = detect_import_state_dialect(obj, None)
        if dialect:
            rec.update(role="import_state",
                       detail="结构推断方言 %s:%s" % (dialect, reason))
            return rec
        if isinstance(obj.get("records"), list):
            rec.update(role="publisher_records",
                       detail="出版方 JSON(records 数组)")
            return rec
        rec.update(detail="未识别的 JSON 对象")
        return rec
    if isinstance(obj, list) and obj and all(isinstance(r, dict) for r in obj):
        rec.update(role="publisher_records", detail="出版方 JSON 数组")
        return rec
    if jsonl_rows is not None:
        if all(_row_has_state_shape(r) for r in jsonl_rows):
            rec.update(role="import_state", detail="结构推断方言 c:JSONL 状态行")
        else:
            rec.update(role="publisher_records", detail="出版方 JSONL")
        return rec
    if name.endswith(".csv"):
        rec.update(role="publisher_records", detail="出版方 CSV(按表头解析)")
        return rec
    rec.update(detail="无法解析为 JSON/JSONL/CSV")
    return rec


# ---------------------------------------------------------------------------
# 当前响应抽取与规范化
# ---------------------------------------------------------------------------

def _crossref_year(item):
    for key in ("issued", "published-print", "published-online", "published"):
        dp = (item.get(key) or {}).get("date-parts")
        if dp and dp[0]:
            return norm_year(dp[0][0])
    return None


def extract_crossref(obj, rel):
    msg = obj.get("message") or {}
    items = msg.get("items") or []
    out = []
    for i, it in enumerate(items):
        authors = []
        for a in it.get("author") or []:
            fam = (a.get("family") or "").strip()
            giv = (a.get("given") or "").strip()
            nm = (fam + " " + giv).strip() or (a.get("name") or "").strip()
            if nm:
                authors.append(nm)
        ct = it.get("container-title") or []
        fields = {
            "title": (it.get("title") or [None])[0],
            "authors": authors,
            "year": _crossref_year(it),
            "venue": ct[0] if ct else None,
            "doi": it.get("DOI"),
            "pmid": None,
        }
        out.append({"source_db": "crossref", "fields": fields,
                    "evidence": {"material": rel,
                                 "locator": "message.items[%d]" % i}})
    info = {"source_db": "crossref", "material": rel, "present": True,
            "items_count": len(items),
            "total_results": msg.get("total-results"),
            "next_cursor": msg.get("next-cursor"), "next_cursor_mark": None}
    return out, info


def extract_europepmc(obj, rel):
    results = ((obj.get("resultList") or {}).get("result")) or []
    out = []
    for i, it in enumerate(results):
        authors = []
        if it.get("authorString"):
            authors = [a.strip() for a in str(it["authorString"]).split(",")
                       if a.strip()]
        pmid = it.get("pmid") or (it.get("id") if it.get("source") == "MED"
                                  else None)
        fields = {
            "title": it.get("title"),
            "authors": authors,
            "year": it.get("pubYear"),
            "venue": it.get("journalTitle"),
            "doi": it.get("doi"),
            "pmid": pmid,
        }
        out.append({"source_db": "europepmc", "fields": fields,
                    "evidence": {"material": rel,
                                 "locator": "resultList.result[%d]" % i}})
    info = {"source_db": "europepmc", "material": rel, "present": True,
            "items_count": len(results), "total_results": obj.get("hitCount"),
            "next_cursor": None,
            "next_cursor_mark": obj.get("nextCursorMark")}
    return out, info


def _publisher_fields(row):
    authors = row.get("authors") or row.get("author")
    if isinstance(authors, str):
        authors = [a.strip() for a in re.split(r"[;|]", authors) if a.strip()]
    year = row.get("year") or row.get("pub_year") or row.get("date")
    venue = row.get("venue") or row.get("journal") or row.get("container")
    raw_id = row.get("id") or row.get("record_id") or row.get("seq")
    return {
        "title": row.get("title"),
        "authors": authors or [],
        "year": year,
        "venue": venue,
        "doi": row.get("doi") or row.get("DOI"),
        "pmid": row.get("pmid") or row.get("PMID"),
        "_raw_id": raw_id,
        "_seq": row.get("seq"),
    }


def extract_publisher(text, obj, jsonl_rows, rel):
    rows = []
    if isinstance(obj, dict) and isinstance(obj.get("records"), list):
        rows = obj["records"]
    elif isinstance(obj, list):
        rows = obj
    elif jsonl_rows is not None:
        rows = jsonl_rows
    elif rel.lower().endswith(".csv"):
        rows = list(csv.DictReader(io.StringIO(text)))
    out = []
    max_seq = None
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        fields = _publisher_fields(row)
        seq = fields.pop("_seq", None)
        raw_id = fields.pop("_raw_id", None)
        if seq is not None:
            try:
                max_seq = max(max_seq or 0, int(seq))
            except (TypeError, ValueError):
                pass
        out.append({"source_db": "publisher", "fields": fields,
                    "raw_id": str(raw_id) if raw_id is not None else None,
                    "evidence": {"material": rel, "locator": "records[%d]" % i}})
    info = {"source_db": "publisher", "material": rel, "present": True,
            "items_count": len(out), "total_results": None,
            "next_cursor": None, "next_cursor_mark": None,
            "max_seq": max_seq}
    return out, info


def make_current_record(source_db, fields, evidence, raw_id=None):
    doi = norm_doi(fields.get("doi"))
    pmid = norm_pmid(fields.get("pmid"))
    if doi:
        identifier = doi
    elif pmid:
        identifier = "pmid:" + pmid
    elif raw_id:
        identifier = "%s:%s" % (source_db, raw_id)
    else:
        identifier = "%s:%s" % (source_db,
                                sha256_json(fields)[:12])
    aliases = []
    if doi:
        aliases.append(["doi", doi])
    if pmid:
        aliases.append(["pmid", pmid])
    if raw_id:
        aliases.append([source_db, str(raw_id)])
    aliases.append([source_db, identifier])
    return {
        "identifier": identifier,
        "source_db": source_db,
        "fields": {k: fields.get(k) for k in
                   ("title", "authors", "year", "venue", "doi", "pmid")},
        "content_fingerprint": fingerprint_fields(fields),
        "aliases": sorted(map(list, {tuple(a) for a in aliases})),
        "present_in_sources": [source_db],
        "evidence": evidence,
    }


# ---------------------------------------------------------------------------
# import_state 方言规范化
# ---------------------------------------------------------------------------

def _state_record(identifier, source_db, content_hash, fields, imported_at,
                  idx):
    identifier = str(identifier)
    if identifier.startswith("doi:"):
        identifier = norm_doi(identifier) or identifier
    elif identifier.upper().startswith("PMID:"):
        identifier = "pmid:" + (norm_pmid(identifier) or identifier[5:])
    aliases = set()
    if looks_like_doi(identifier):
        aliases.add(("doi", norm_doi(identifier)))
    elif identifier.startswith("pmid:"):
        aliases.add(("pmid", norm_pmid(identifier)))
    aliases.add((source_db or "unknown", identifier))
    if fields:
        if fields.get("doi"):
            aliases.add(("doi", norm_doi(fields["doi"])))
        if fields.get("pmid"):
            aliases.add(("pmid", norm_pmid(fields["pmid"])))
    return {
        "identifier": identifier,
        "source_db": source_db or "unknown",
        "content_hash": content_hash,
        "fields": fields,
        "imported_at": imported_at,
        "state_index": idx,
        "aliases": sorted([list(a) for a in aliases if a[1]]),
    }


def normalize_import_state(obj, jsonl_rows, dialect, rel, file_sha):
    """三种方言 → 统一 previous_state 记录列表。"""
    records = []
    watermarks = {}
    stores_fields = False
    if dialect == "a":
        watermarks = obj.get("watermarks") or {}
        for i, r in enumerate(obj.get("records") or []):
            ident = r.get("identifier") or r.get("doi") or r.get("pmid")
            if ident is None:
                continue
            if "pmid" in r and "identifier" not in r and "doi" not in r:
                ident = "pmid:%s" % ident
            ch = None
            for k in HASH_KEYS:
                if r.get(k):
                    ch = r[k]
                    break
            fields = r.get("fields") if isinstance(r.get("fields"), dict) \
                else None
            if fields:
                stores_fields = True
            imported_at = r.get("imported_at", r.get("seq"))
            records.append(_state_record(ident, r.get("source_db"), ch,
                                         fields, imported_at, i))
    elif dialect == "b":
        for i, ident in enumerate(sorted(obj.keys())):
            v = obj[ident]
            ch = None
            for k in HASH_KEYS:
                if v.get(k):
                    ch = v[k]
                    break
            fields = v.get("fields") if isinstance(v.get("fields"), dict) \
                else None
            if fields:
                stores_fields = True
            records.append(_state_record(ident, v.get("source_db"), ch,
                                         fields, v.get("imported_at"), i))
    elif dialect == "c":
        for i, r in enumerate(jsonl_rows):
            ident = r.get("identifier") or r.get("doi") or r.get("pmid")
            if ident is None:
                continue
            if "pmid" in r and "identifier" not in r and "doi" not in r:
                ident = "pmid:%s" % ident
            ch = None
            for k in HASH_KEYS:
                if r.get(k):
                    ch = r[k]
                    break
            fields = r.get("fields") if isinstance(r.get("fields"), dict) \
                else None
            if fields:
                stores_fields = True
            records.append(_state_record(ident, r.get("source_db"), ch,
                                         fields, r.get("imported_at"), i))
    return {"dialect": dialect, "baseline_established": False,
            "stores_fields": stores_fields, "watermarks": watermarks,
            "records": records, "source_file": rel,
            "source_sha256": file_sha}


def empty_previous_state(note):
    return {"dialect": None, "baseline_established": True,
            "baseline_note": note, "stores_fields": False,
            "watermarks": {}, "records": [], "source_file": None,
            "source_sha256": None}


# ---------------------------------------------------------------------------
# 输入发现与 case 读取
# ---------------------------------------------------------------------------

def load_case(input_dir):
    """返回 (case, error)。case.json 缺失/不可解析/缺 case_id → error。"""
    path = os.path.join(input_dir, "case.json")
    if not os.path.exists(path):
        return None, "case.json 不存在:%s" % path
    try:
        case = load_json(path)
    except Exception as e:
        return None, "case.json 不可解析:%s" % e
    if not isinstance(case, dict) or not case.get("case_id"):
        return None, "case.json 缺少 case_id"
    return case, None


def discover_materials(input_dir, case):
    """确定性排序的材料清单(相对路径),不含 case.json/task.md。"""
    rels = []
    for m in (case.get("materials") or []):
        rels.append(m)
    mdir = os.path.join(input_dir, "materials")
    if os.path.isdir(mdir):
        for name in sorted(os.listdir(mdir)):
            rel = os.path.join("materials", name)
            if os.path.isfile(os.path.join(input_dir, rel)) \
                    and rel not in rels:
                rels.append(rel)
    return sorted(set(rels))


# ---------------------------------------------------------------------------
# parse:嗅探 + previous_state + current_state
# ---------------------------------------------------------------------------

def run_parse(input_dir, work_dir):
    """返回 (exit_code, context)。2 = import_state 结构嗅探失败(诚实降级)。"""
    case, err = load_case(input_dir)
    if err:
        return 3, {"error": err}
    os.makedirs(work_dir, exist_ok=True)
    rels = discover_materials(input_dir, case)
    sniffs = []
    for rel in rels:
        path = os.path.join(input_dir, rel)
        if not os.path.exists(path):
            sniffs.append({"path": rel, "role": "missing",
                           "detail": "case.json 声明但磁盘不存在", "sha256": None})
            continue
        sniffs.append(sniff_material(path, rel))

    # --- import_state ---
    state_sniffs = [s for s in sniffs if s["role"] in
                    ("import_state", "import_state_unknown")]
    sniff_report = {
        "case_id": case["case_id"], "generated_by": TOOL_NAME,
        "materials": sniffs,
        "import_state_candidates": [s["path"] for s in state_sniffs],
    }
    previous = None
    degraded = None
    if not state_sniffs:
        previous = empty_previous_state(
            "材料中未发现 import_state;本次视为首次导入,全部当前记录分类为 "
            "new,并声明 baseline_established")
    elif any(s["role"] == "import_state_unknown" for s in state_sniffs) \
            and not any(s["role"] == "import_state" for s in state_sniffs):
        bad = [s for s in state_sniffs if s["role"] == "import_state_unknown"][0]
        degraded = ("import_state 结构嗅探失败(%s):%s;不猜测结构,诚实降级"
                    % (bad["path"], bad["detail"]))
        sniff_report["sniff_failure"] = degraded
    else:
        s = [x for x in state_sniffs if x["role"] == "import_state"][0]
        path = os.path.join(input_dir, s["path"])
        text = _read_text(path)
        obj = _try_json(text)
        jsonl_rows = None if obj is not None else _try_jsonl(text)
        dialect, reason = detect_import_state_dialect(obj, jsonl_rows)
        if not dialect:
            degraded = ("import_state 结构嗅探失败(%s):%s;不猜测结构,诚实降级"
                        % (s["path"], reason))
            sniff_report["sniff_failure"] = degraded
        else:
            previous = normalize_import_state(obj, jsonl_rows, dialect,
                                              s["path"], s["sha256"])
            previous["dialect_reason"] = reason
    write_json(os.path.join(work_dir, "sniff_report.json"), sniff_report)

    # --- 当前响应快照 ---
    current_records = []
    source_infos = {}
    for s in sniffs:
        if s["role"] not in ("crossref_response", "europepmc_response",
                             "publisher_records"):
            continue
        path = os.path.join(input_dir, s["path"])
        text = _read_text(path)
        obj = _try_json(text)
        jsonl_rows = None if obj is not None else _try_jsonl(text)
        if s["role"] == "crossref_response":
            recs, info = extract_crossref(obj, s["path"])
        elif s["role"] == "europepmc_response":
            recs, info = extract_europepmc(obj, s["path"])
        else:
            recs, info = extract_publisher(text, obj, jsonl_rows, s["path"])
        db = info["source_db"]
        if db in source_infos:  # 同库多份响应:合并计数,游标信息取首份并声明
            prev_info = source_infos[db]
            prev_info["items_count"] += info["items_count"]
            prev_info.setdefault("additional_materials", []).append(s["path"])
            prev_info["cursor_note"] = "同库多份响应;游标信息以首份为准"
        else:
            source_infos[db] = info
        for r in recs:
            current_records.append(make_current_record(
                r["source_db"], r["fields"], r["evidence"],
                raw_id=r.get("raw_id")))

    # 跨响应重复标识符:合并 present_in_sources(保留首次证据)
    by_ident = {}
    for r in current_records:
        if r["identifier"] in by_ident:
            prev = by_ident[r["identifier"]]
            for src in r["present_in_sources"]:
                if src not in prev["present_in_sources"]:
                    prev["present_in_sources"].append(src)
            prev.setdefault("duplicate_observations", []).append(r["evidence"])
        else:
            by_ident[r["identifier"]] = r
    current_records = [by_ident[k] for k in sorted(by_ident.keys())]

    current = {"case_id": case["case_id"], "generated_by": TOOL_NAME,
               "records": current_records,
               "sources": [source_infos[k] for k in sorted(source_infos.keys())]}
    write_json(os.path.join(work_dir, "current_state.json"), current)

    if previous is None:
        previous = empty_previous_state(
            "import_state 嗅探失败,无可用上一状态")
        previous["sniff_failed"] = True
    write_json(os.path.join(work_dir, "previous_state.json"), previous)

    ctx = {"case": case, "sniffs": sniffs, "degraded": degraded,
           "previous": previous, "current": current}
    if degraded:
        return 2, ctx
    return 0, ctx


# ---------------------------------------------------------------------------
# diff:六路分类
# ---------------------------------------------------------------------------

SOURCE_ID_VALID = {
    "crossref": lambda ident: looks_like_doi(ident),
    "europepmc": lambda ident: bool(re.fullmatch(r"pmid:\d+", str(ident)))
    or looks_like_doi(ident),
    "publisher": lambda ident: bool(str(ident).strip()),
}


def state_row_contradiction(rec):
    """状态行自相矛盾检测:identifier 与自带 fields 中的 id 冲突。"""
    f = rec.get("fields") or {}
    ident = rec["identifier"]
    if looks_like_doi(ident) and f.get("doi") \
            and norm_doi(f["doi"]) != norm_doi(ident):
        return "identifier(%s) 与 fields.doi(%s) 冲突" % (ident, f["doi"])
    if ident.startswith("pmid:") and f.get("pmid") \
            and norm_pmid(f["pmid"]) != norm_pmid(ident):
        return "identifier(%s) 与 fields.pmid(%s) 冲突" % (ident, f["pmid"])
    return None


def field_level_diffs(old_fields, new_fields):
    diffs = []
    for k in FINGERPRINT_FIELDS:
        ov = (old_fields or {}).get(k)
        nv = (new_fields or {}).get(k)
        if k in ("title", "venue"):
            ov, nv = norm_text(ov), norm_text(nv)
        elif k == "year":
            ov, nv = norm_year(ov), norm_year(nv)
        elif k == "doi":
            ov, nv = norm_doi(ov), norm_doi(nv)
        elif k == "pmid":
            ov, nv = norm_pmid(ov), norm_pmid(nv)
        elif k == "authors":
            ov = [norm_text(a) for a in (ov or [])]
            nv = [norm_text(a) for a in (nv or [])]
        if ov != nv:
            diffs.append({"field": k, "before": ov, "after": nv})
    return diffs


def run_diff(work_dir):
    previous = load_json(os.path.join(work_dir, "previous_state.json"))
    current = load_json(os.path.join(work_dir, "current_state.json"))
    sources_present = sorted({s["source_db"] for s in current["sources"]})
    cur_by_alias = {}
    for rec in current["records"]:
        for a in rec["aliases"]:
            cur_by_alias.setdefault(tuple(a), []).append(rec)

    entries = []
    matched_current = set()

    for srec in previous["records"]:
        # 先匹配当前记录(按别名)
        match = None
        for a in srec["aliases"]:
            cands = cur_by_alias.get(tuple(a))
            if cands:
                match = sorted(cands, key=lambda r: r["identifier"])[0]
                break
        base = {"identifier": srec["identifier"],
                "source_db_claimed": srec["source_db"],
                "content_hash_previous": srec["content_hash"],
                "evidence": {"state_record_index": srec["state_index"],
                             "state_file": previous.get("source_file")}}
        if match is not None:
            matched_current.add(match["identifier"])
            base["evidence"]["current"] = match["evidence"]
            base["present_in_sources"] = match["present_in_sources"]
            base["content_fingerprint_current"] = match["content_fingerprint"]
            if srec["source_db"] != match["source_db"]:
                base["source_db_mismatch"] = (
                    "state 记为 %s,当前出现于 %s" % (srec["source_db"],
                                                   match["source_db"]))
            if srec["content_hash"] \
                    and srec["content_hash"] == match["content_fingerprint"]:
                base["class"] = "unchanged"
            else:
                base["class"] = "changed"
                if srec.get("fields"):
                    base["field_diffs"] = field_level_diffs(
                        srec["fields"], match["fields"])
                    base["changed_fields_unavailable"] = False
                else:
                    base["field_diffs"] = None
                    base["changed_fields_unavailable"] = True
            entries.append(base)
            continue
        # 未匹配:撤回/不可核验/不一致 三选一
        src = srec["source_db"]
        contradiction = state_row_contradiction(srec)
        shape_ok = SOURCE_ID_VALID.get(src, lambda i: True)(srec["identifier"])
        if src not in sources_present:
            base["class"] = "unverifiable_withdrawal"
            base["subclass"] = "source_absent_too"
            base["detail"] = ("其来源库 %s 的响应本次缺席,无法区分"
                              "'记录被撤回'与'源未提供',不可核验" % src)
        elif contradiction:
            base["class"] = "inconsistent_state"
            base["detail"] = ("状态行自相矛盾(%s),且该标识符未出现于 %s "
                              "响应;状态本身不可信,需人工裁定"
                              % (contradiction, src))
        elif not shape_ok:
            base["class"] = "inconsistent_state"
            base["detail"] = ("标识符 %s 不符合来源库 %s 的标识符形态,"
                              "状态声称的导入事实与源模式矛盾"
                              % (srec["identifier"], src))
        else:
            base["class"] = "withdrawn"
            base["subclass"] = "source_present_but_record_gone"
            base["detail"] = ("来源库 %s 的响应在场,但该记录已不在其中;"
                              "作为'导入治理事实'登记为撤回。是否为撤稿/"
                              "删除的语义判定不属于本技能,应移交专门的"
                              "撤回分析流程" % src)
        entries.append(base)

    for rec in current["records"]:
        if rec["identifier"] in matched_current:
            continue
        entries.append({"identifier": rec["identifier"], "class": "new",
                        "source_db_claimed": rec["source_db"],
                        "present_in_sources": rec["present_in_sources"],
                        "content_fingerprint_current":
                            rec["content_fingerprint"],
                        "content_hash_previous": None,
                        "evidence": {"current": rec["evidence"]}})

    entries.sort(key=lambda e: (e["identifier"],))
    counts = {c: 0 for c in CLASSES}
    for e in entries:
        counts[e["class"]] += 1
    union_size = len(entries)
    diff = {
        "case_id": current["case_id"],
        "generated_by": TOOL_NAME,
        "baseline_established": previous.get("baseline_established", False),
        "state_dialect": previous.get("dialect"),
        "sources_present": sources_present,
        "sources_absent": sorted({r["source_db"] for r in previous["records"]}
                                 - set(sources_present)),
        "counts": dict(counts, union_size=union_size,
                       previous_records=len(previous["records"]),
                       current_records=len(current["records"])),
        "entries": entries,
    }
    # 分区不变量:六类互不重叠且完备
    assert sum(counts.values()) == union_size
    write_json(os.path.join(work_dir, "import_diff.json"), diff)
    return 0, {"diff": diff, "previous": previous, "current": current}


# ---------------------------------------------------------------------------
# watermark:推进提案(绝不写回输入状态)
# ---------------------------------------------------------------------------

def _wm_get(wm, *keys):
    for k in keys:
        if isinstance(wm, dict) and wm.get(k) is not None:
            return wm[k], k
    return None, None


def propose_db_watermark(db, prev_wm, info):
    """返回 {previous, proposed, action, hold_reason, evidence}。

    action ∈ advance / hold / initialize。规则详见
    references/watermark-policy.md;任何回归(proposed < previous,数值键)
    都被拦截为 hold。"""
    prev = prev_wm if isinstance(prev_wm, dict) else {}
    out = {"previous": prev or None, "proposed": None, "action": "hold",
           "hold_reason": None, "evidence": None}
    if info is None or not info.get("present"):
        out["hold_reason"] = "response_absent:本次材料中无 %s 响应" % db
        return out
    if db == "crossref":
        proposed = dict(prev)
        moved = []
        if info.get("next_cursor"):
            proposed["cursor"] = info["next_cursor"]
            moved.append("cursor←响应 next-cursor")
        if info.get("items_count"):
            prev_off, ok_key = _wm_get(prev, "offset")
            prev_off = int(prev_off) if prev_off is not None else 0
            proposed["offset"] = prev_off + info["items_count"]
            moved.append("offset←%d+%d" % (prev_off, info["items_count"]))
        if not moved:
            out["hold_reason"] = "no_progress_signal:响应无 next-cursor 且无条目"
            return out
        out.update(proposed=proposed,
                   action="advance" if prev else "initialize",
                   evidence=";".join(moved))
        return out
    if db == "europepmc":
        prev_mark, _ = _wm_get(prev, "cursorMark", "cursor")
        new_mark = info.get("next_cursor_mark")
        if new_mark and new_mark != prev_mark:
            proposed = dict(prev)
            proposed["cursorMark"] = new_mark
            out.update(proposed=proposed,
                       action="advance" if prev else "initialize",
                       evidence="cursorMark←响应 nextCursorMark")
            return out
        out["hold_reason"] = ("no_progress_signal:响应无 nextCursorMark 或与"
                              "现值相同(深分页无推进)")
        return out
    if db == "publisher":
        if info.get("max_seq") is not None:
            prev_seq, _ = _wm_get(prev, "last_seq", "last_id", "offset")
            prev_seq = int(prev_seq) if prev_seq is not None else -1
            if info["max_seq"] > prev_seq:
                proposed = dict(prev)
                proposed["last_seq"] = info["max_seq"]
                out.update(proposed=proposed,
                           action="advance" if prev else "initialize",
                           evidence="last_seq←响应中最大 seq(%d)"
                                    % info["max_seq"])
                return out
            out["hold_reason"] = "regression_guard:响应最大 seq 未超过现水印"
            return out
        out["hold_reason"] = ("no_cursor_semantics:出版方导出无游标语义,"
                              "仅可按 seq 推进,而响应中无 seq")
        return out
    out["hold_reason"] = "no_advance_rule:未知来源库 %s,无推进规则" % db
    return out


def run_watermark(work_dir):
    previous = load_json(os.path.join(work_dir, "previous_state.json"))
    current = load_json(os.path.join(work_dir, "current_state.json"))
    infos = {s["source_db"]: s for s in current["sources"]}
    prev_wms = previous.get("watermarks") or {}
    dbs = sorted(set(prev_wms.keys()) | set(infos.keys()))
    proposals = {}
    n_adv = n_hold = 0
    for db in dbs:
        p = propose_db_watermark(db, prev_wms.get(db), infos.get(db))
        # 回归守卫(数值键):proposed 任何数值键不得小于 previous
        if p["action"] == "advance" and p["previous"] and p["proposed"]:
            for k, v in p["proposed"].items():
                if isinstance(v, (int, float)) and \
                        isinstance(p["previous"].get(k), (int, float)) \
                        and v < p["previous"][k]:
                    p["action"] = "hold"
                    p["hold_reason"] = "regression_guard:%s 回退(%s→%s)" % (
                        k, p["previous"][k], v)
                    p["proposed"] = None
                    break
        proposals[db] = p
        if p["action"] == "advance":
            n_adv += 1
        else:
            n_hold += 1
    summary = ("水印提案:%d 个库推进(%s),%d 个库保持(%s)。"
               "本提案 requires_approval=true,未经组织者显式批准绝不写回。"
               % (n_adv,
                  ",".join(sorted(k for k, v in proposals.items()
                                  if v["action"] in ("advance", "initialize")))
                  or "无",
                  n_hold,
                  ",".join(sorted(k for k, v in proposals.items()
                                  if v["action"] == "hold")) or "无"))
    state_sha = None
    if previous.get("source_file") and previous.get("source_sha256"):
        state_sha = previous["source_sha256"]
    proposal = {
        "case_id": current["case_id"],
        "generated_by": TOOL_NAME,
        "requires_approval": True,
        "applied": False,
        "base_state_file": previous.get("source_file"),
        "base_state_sha256": state_sha,
        "watermarks": proposals,
        "diff_summary": summary,
    }
    write_json(os.path.join(work_dir, "proposed_next_state.json"), proposal)
    return 0, {"proposal": proposal}


# ---------------------------------------------------------------------------
# apply-dispositions:折叠模型处置决定 → final_governed_state.json
# ---------------------------------------------------------------------------

def run_apply_dispositions(work_dir, output_dir, dispositions_path):
    diff = load_json(os.path.join(work_dir, "import_diff.json"))
    previous = load_json(os.path.join(work_dir, "previous_state.json"))
    current = load_json(os.path.join(work_dir, "current_state.json"))
    try:
        disp_doc = load_json(dispositions_path)
    except Exception as e:
        return 2, {"error": "dispositions 文件不可解析:%s" % e}
    disps = disp_doc.get("dispositions") if isinstance(disp_doc, dict) \
        else disp_doc
    if not isinstance(disps, list):
        return 2, {"error": "dispositions 文件须为数组或含 dispositions 数组"}
    entry_by_ident = {e["identifier"]: e for e in diff["entries"]}
    errors = []
    applied = []
    seen = set()
    for i, d in enumerate(disps):
        ident = d.get("identifier")
        act = d.get("disposition")
        if not ident or not act:
            errors.append("第 %d 条缺 identifier/disposition" % i)
            continue
        if ident not in entry_by_ident:
            errors.append("第 %d 条 identifier 未知:%s" % (i, ident))
            continue
        cls = entry_by_ident[ident]["class"]
        if act not in ALLOWED_DISPOSITIONS.get(cls, []):
            errors.append("第 %d 条:%s 类别不允许 %s" % (i, cls, act))
            continue
        if ident in seen:
            errors.append("第 %d 条:重复处置 %s" % (i, ident))
            continue
        seen.add(ident)
        applied.append({"identifier": ident, "class": cls,
                        "disposition": act,
                        "rationale": d.get("rationale")})
    if errors:
        return 2, {"error": "dispositions 校验失败", "details": errors}

    cur_by_ident = {r["identifier"]: r for r in current["records"]}
    prev_by_ident = {r["identifier"]: r for r in previous["records"]}
    # 别名→当前记录(changed accept 时用)
    cur_by_alias = {}
    for r in current["records"]:
        for a in r["aliases"]:
            cur_by_alias.setdefault(tuple(a), r)

    governed = []
    change_records = []
    for e in diff["entries"]:
        ident = e["identifier"]
        cls = e["class"]
        disp = next((a for a in applied if a["identifier"] == ident), None)
        act = disp["disposition"] if disp else None
        if cls == "new":
            rec = cur_by_ident[ident]
            governed.append({"identifier": ident,
                             "source_db": rec["source_db"],
                             "content_hash": rec["content_fingerprint"],
                             "fields": rec["fields"],
                             "governance": {"origin": "current_response",
                                            "note": "本轮新增,自动纳入治理状态"}})
            change_records.append({"identifier": ident, "class": cls,
                                   "action": "admit_new",
                                   "detail": "新记录纳入治理状态"})
        elif cls == "unchanged":
            prev = prev_by_ident[ident]
            governed.append({"identifier": ident,
                             "source_db": prev["source_db"],
                             "content_hash": prev["content_hash"],
                             "fields": prev.get("fields"),
                             "governance": {"origin": "previous_state",
                                            "note": "指纹一致,原样保留"}})
        elif cls == "changed":
            prev = prev_by_ident.get(ident)
            cur = None
            for a in (prev or {}).get("aliases", []):
                if tuple(a) in cur_by_alias:
                    cur = cur_by_alias[tuple(a)]
                    break
            if act == "accept_change" and cur is not None:
                governed.append({"identifier": ident,
                                 "source_db": cur["source_db"],
                                 "content_hash": cur["content_fingerprint"],
                                 "fields": cur["fields"],
                                 "governance": {"origin": "current_response",
                                                "note": "accept_change:"
                                                "采纳当前值",
                                                "rationale":
                                                    disp["rationale"]}})
                change_records.append({"identifier": ident, "class": cls,
                                       "action": "accept_change",
                                       "detail": json.dumps(
                                           e.get("field_diffs"),
                                           ensure_ascii=False)})
            else:
                note = ("keep_previous:保留上一状态值" if act == "keep_previous"
                        else "escalate:待人工裁定,暂保留上一状态值")
                governed.append({"identifier": ident,
                                 "source_db": (prev or {}).get("source_db",
                                                               "unknown"),
                                 "content_hash": (prev or {}).get(
                                     "content_hash"),
                                 "fields": (prev or {}).get("fields"),
                                 "governance": {"origin": "previous_state",
                                                "note": note,
                                                "flag": act or "pending",
                                                "rationale":
                                                    disp["rationale"] if disp
                                                    else None}})
                change_records.append({"identifier": ident, "class": cls,
                                       "action": act or "pending",
                                       "detail": note})
        elif cls == "withdrawn":
            if act == "exclude_withdrawn":
                change_records.append({"identifier": ident, "class": cls,
                                       "action": "exclude_withdrawn",
                                       "detail": "按撤回事实从治理状态移除;"
                                       "撤回语义判定移交专门流程"})
                continue  # 不进入治理状态
            prev = prev_by_ident[ident]
            note = ("keep_previous:保留并标注待核验" if act == "keep_previous"
                    else "escalate:待人工裁定,暂保留")
            governed.append({"identifier": ident, "source_db":
                             prev["source_db"],
                             "content_hash": prev["content_hash"],
                             "fields": prev.get("fields"),
                             "governance": {"origin": "previous_state",
                                            "note": note, "flag":
                                                act or "pending_withdrawn",
                                            "rationale": disp["rationale"]
                                            if disp else None}})
            change_records.append({"identifier": ident, "class": cls,
                                   "action": act or "pending",
                                   "detail": note})
        else:  # unverifiable_withdrawal / inconsistent_state
            prev = prev_by_ident[ident]
            note = ("keep_previous:保留原记录" if act == "keep_previous"
                    else "escalate:待人工裁定,暂保留原记录")
            governed.append({"identifier": ident,
                             "source_db": prev["source_db"],
                             "content_hash": prev["content_hash"],
                             "fields": prev.get("fields"),
                             "governance": {"origin": "previous_state",
                                            "note": note,
                                            "flag": act or "pending",
                                            "class": cls,
                                            "rationale": disp["rationale"]
                                            if disp else None}})
            change_records.append({"identifier": ident, "class": cls,
                                   "action": act or "pending",
                                   "detail": note})

    governed.sort(key=lambda r: r["identifier"])
    final_state = {
        "case_id": diff["case_id"],
        "generated_by": TOOL_NAME,
        "note": ("治理后的记录状态。水印保持上一状态原值 —— 推进提案见 "
                 "proposed_next_state.json,requires_approval=true,"
                 "本技能绝不静默写回组织者状态。"),
        "watermarks": previous.get("watermarks") or {},
        "watermark_status": "held_pending_approval",
        "records": governed,
        "applied_dispositions": applied,
        "pending_review": sorted(
            e["identifier"] for e in diff["entries"]
            if e["class"] in REVIEW_CLASSES
            and e["identifier"] not in {a["identifier"] for a in applied}),
    }
    os.makedirs(output_dir, exist_ok=True)
    write_json(os.path.join(output_dir, "final_governed_state.json"),
               final_state)
    return 0, {"final_state": final_state, "applied": applied,
               "change_records": change_records}


# ---------------------------------------------------------------------------
# report:delta_report.md
# ---------------------------------------------------------------------------

def _fmt_val(v):
    if v is None:
        return "∅"
    if isinstance(v, list):
        return "; ".join(str(x) for x in v) or "∅"
    return str(v)


def run_report(work_dir, output_dir, applied=None):
    diff = load_json(os.path.join(work_dir, "import_diff.json"))
    proposal_path = os.path.join(work_dir, "proposed_next_state.json")
    proposal = load_json(proposal_path) if os.path.exists(proposal_path) \
        else None
    c = diff["counts"]
    L = []
    L.append("# 增量导入治理差异报告(delta report)")
    L.append("")
    L.append("- case_id:`%s`" % diff["case_id"])
    L.append("- 状态方言:`%s`;基线建立:`%s`" % (
        diff.get("state_dialect"), diff.get("baseline_established")))
    L.append("- 在场来源库:%s;缺席来源库:%s" % (
        ", ".join(diff["sources_present"]) or "无",
        ", ".join(diff["sources_absent"]) or "无"))
    L.append("")
    L.append("## 1. 分类计数")
    L.append("")
    L.append("| 类别 | 数量 |")
    L.append("| --- | ---: |")
    L.append("| 上一状态记录数 | %d |" % c["previous_records"])
    L.append("| 当前响应记录数 | %d |" % c["current_records"])
    for k, zh in [("new", "新增"), ("unchanged", "不变"), ("changed", "变更"),
                  ("withdrawn", "撤回(源在场而记录消失)"),
                  ("unverifiable_withdrawal", "不可核验撤回(源亦缺席)"),
                  ("inconsistent_state", "状态不一致")]:
        L.append("| %s `%s` | %d |" % (zh, k, c[k]))
    L.append("| **标识符并集** | **%d** |" % c["union_size"])
    L.append("")
    part_ok = (c["new"] + c["unchanged"] + c["changed"] + c["withdrawn"]
               + c["unverifiable_withdrawal"] + c["inconsistent_state"]
               == c["union_size"])
    L.append("分区校验:%s(六类之和 = 并集大小,互不重叠、无一遗漏)。"
             % ("通过" if part_ok else "**失败**"))
    L.append("")

    def _table(title, rows, header, render):
        L.append(title)
        L.append("")
        if not rows:
            L.append("（无）")
            L.append("")
            return
        L.append("| " + " | ".join(header) + " |")
        L.append("| " + " | ".join("---" for _ in header) + " |")
        for r in rows:
            L.append("| " + " | ".join(render(r)) + " |")
        L.append("")

    news = [e for e in diff["entries"] if e["class"] == "new"]
    _table("## 2. 新增记录(new)", news,
           ["标识符", "来源库", "证据"],
           lambda e: ["`%s`" % e["identifier"], e["source_db_claimed"],
                      "`%s`" % e["evidence"]["current"]["locator"]])

    changed = [e for e in diff["entries"] if e["class"] == "changed"]
    L.append("## 3. 变更记录(changed,field 级 before→after)")
    L.append("")
    if not changed:
        L.append("（无）")
        L.append("")
    for e in changed:
        L.append("### `%s`(来源库:%s)" % (e["identifier"],
                                          e["source_db_claimed"]))
        L.append("")
        if e.get("changed_fields_unavailable"):
            L.append("上一状态方言不存储字段值,**field 级差异不可得**"
                     "(changed_fields_unavailable):仅知内容指纹 "
                     "`%s` → `%s`。" % (e.get("content_hash_previous"),
                                        e.get("content_fingerprint_current")))
        else:
            L.append("| 字段 | before(上一状态) | after(当前响应) |")
            L.append("| --- | --- | --- |")
            for d in e.get("field_diffs") or []:
                L.append("| %s | %s | %s |" % (
                    d["field"], _fmt_val(d["before"]), _fmt_val(d["after"])))
        L.append("")

    withdrawn = [e for e in diff["entries"]
                 if e["class"] in ("withdrawn", "unverifiable_withdrawal")]
    _table("## 4. 撤回与不可核验撤回", withdrawn,
           ["标识符", "声称来源库", "子类", "说明"],
           lambda e: ["`%s`" % e["identifier"], e["source_db_claimed"],
                      "`%s`" % e.get("subclass", "-"), e.get("detail", "")])
    L.append("> 边界声明:此处仅登记「记录已不在响应中」的**导入治理事实**;"
             "撤稿/删除的语义判定(retraction analysis)不属于本技能,"
             "应移交专门流程。")
    L.append("")

    inc = [e for e in diff["entries"] if e["class"] == "inconsistent_state"]
    _table("## 5. 状态不一致(inconsistent_state)", inc,
           ["标识符", "声称来源库", "说明"],
           lambda e: ["`%s`" % e["identifier"], e["source_db_claimed"],
                      e.get("detail", "")])

    L.append("## 6. 水印推进提案(requires_approval=true,未写回)")
    L.append("")
    if proposal:
        L.append("| 数据库 | 上一水印 | 提议水印 | 动作 | 保持原因/证据 |")
        L.append("| --- | --- | --- | --- | --- |")
        for db in sorted(proposal["watermarks"].keys()):
            p = proposal["watermarks"][db]
            L.append("| %s | `%s` | `%s` | %s | %s |" % (
                db,
                _canon(p["previous"]) if p["previous"] is not None else "∅",
                _canon(p["proposed"]) if p["proposed"] is not None else "∅",
                p["action"],
                p.get("hold_reason") or p.get("evidence") or ""))
        L.append("")
        L.append(proposal["diff_summary"])
    else:
        L.append("（未生成提案）")
    L.append("")
    L.append("## 7. 批准清单(approval checklist)")
    L.append("")
    L.append("- [ ] 审阅第 3 节全部 changed 条目的 before→after 是否正确")
    L.append("- [ ] 审阅第 4 节撤回/不可核验撤回条目的处置决定")
    L.append("- [ ] 裁定第 5 节 inconsistent_state 条目")
    L.append("- [ ] 显式批准或拒绝第 6 节水印提案(批准前状态文件保持原值)")
    L.append("- [ ] 确认本报告的撤回条目已按需移交撤回语义分析流程")
    L.append("")
    if applied:
        L.append("## 8. 已应用的处置决定(dispositions)")
        L.append("")
        L.append("| 标识符 | 类别 | 处置 | 理由 |")
        L.append("| --- | --- | --- | --- |")
        for a in applied:
            L.append("| `%s` | %s | %s | %s |" % (
                a["identifier"], a["class"], a["disposition"],
                a.get("rationale") or ""))
        L.append("")
    os.makedirs(output_dir, exist_ok=True)
    write_text(os.path.join(output_dir, "delta_report.md"),
               "\n".join(L) + "\n")
    return 0, {}


# ---------------------------------------------------------------------------
# finalize:result.json
# ---------------------------------------------------------------------------

def build_contract_values(case, diff, proposal, applied, degraded):
    """output_contract 字段的确定性映射;未知名 → (None, 未解析)。"""
    counts_public = {
        "previous_records": diff["counts"]["previous_records"],
        "current_records": diff["counts"]["current_records"],
        "new": diff["counts"]["new"], "changed": diff["counts"]["changed"],
        "unchanged": diff["counts"]["unchanged"],
        "withdrawn": diff["counts"]["withdrawn"],
        "unverifiable_withdrawal": diff["counts"]["unverifiable_withdrawal"],
        "inconsistent": diff["counts"]["inconsistent_state"],
    }
    changed_diffs = []
    for e in diff["entries"]:
        if e["class"] != "changed":
            continue
        if e.get("field_diffs"):
            for d in e["field_diffs"]:
                changed_diffs.append({"identifier": e["identifier"],
                                      "field": d["field"],
                                      "before": d["before"],
                                      "after": d["after"]})
        else:
            changed_diffs.append({"identifier": e["identifier"],
                                  "field": None, "before": None,
                                  "after": None,
                                  "changed_fields_unavailable": True})
    c = diff["counts"]
    summary = ("本次对账:上一状态 %d 条、当前响应 %d 条、标识符并集 %d 条;"
               "新增 %d、不变 %d、变更 %d、撤回 %d、不可核验撤回 %d、"
               "状态不一致 %d。水印提案 requires_approval=true,"
               "未经批准不写回。" % (
                   c["previous_records"], c["current_records"],
                   c["union_size"], c["new"], c["unchanged"], c["changed"],
                   c["withdrawn"], c["unverifiable_withdrawal"],
                   c["inconsistent_state"]))
    wm_section = None
    if proposal:
        wm_section = {"requires_approval": True, "applied": False,
                      "watermarks": proposal["watermarks"],
                      "diff_summary": proposal["diff_summary"]}
    mappers = {
        "import_classification_counts": lambda: counts_public,
        "classification_counts": lambda: counts_public,
        "diff_counts": lambda: counts_public,
        "changed_field_diffs": lambda: changed_diffs,
        "changed_records": lambda: changed_diffs,
        "changed_entries": lambda: changed_diffs,
        "watermark_proposal": lambda: wm_section,
        "proposed_watermarks": lambda: wm_section,
        "delta_report_path": lambda: "delta_report.md",
        "delta_report": lambda: "delta_report.md",
        "governance_summary": lambda: summary,
        "import_summary": lambda: summary,
        "delta_summary": lambda: summary,
        "final_governed_state_path": lambda: (
            "final_governed_state.json" if applied is not None else None),
    }
    values, unresolved = {}, []
    for f in (case.get("output_contract") or {}).get("fields") or []:
        name = f.get("name")
        fn = mappers.get(name or "")
        if fn is None:
            values[name] = None
            unresolved.append(name)
        else:
            v = fn()
            values[name] = v
            if v is None:
                unresolved.append(name)
    return values, unresolved, counts_public, summary


def run_finalize(input_dir, work_dir, output_dir, degraded=None,
                 dispositions_pending=False, selfcheck_report=None,
                 applied=None, change_records=None):
    case, err = load_case(input_dir)
    if err:
        return 3, {"error": err}
    diff_path = os.path.join(work_dir, "import_diff.json")
    diff = load_json(diff_path) if os.path.exists(diff_path) else None
    proposal_path = os.path.join(work_dir, "proposed_next_state.json")
    proposal = load_json(proposal_path) if os.path.exists(proposal_path) \
        else None

    sources = [{"path": "case.json",
                "sha256": sha256_file(os.path.join(input_dir, "case.json")),
                "role": "case"}]
    task_path = os.path.join(input_dir, "task.md")
    if os.path.exists(task_path):
        sources.append({"path": "task.md", "sha256": sha256_file(task_path),
                        "role": "task"})
    for rel in discover_materials(input_dir, case):
        p = os.path.join(input_dir, rel)
        sources.append({"path": rel,
                        "sha256": sha256_file(p) if os.path.exists(p)
                        else None,
                        "role": "material"})

    uncertainty = []
    checks = []
    if diff is None:
        status = "partial"
        uncertainty.append({"kind": "pipeline_incomplete",
                            "detail": degraded or "import_diff.json 未生成"})
        if degraded:
            uncertainty.append({"kind": "sniff_degradation",
                                "detail": degraded})
        counts_public = None
        contract_values, unresolved = {}, []
    else:
        contract_values, unresolved, counts_public, _sum = \
            build_contract_values(case, diff, proposal, applied, degraded)
        for e in diff["entries"]:
            if e["class"] == "unverifiable_withdrawal":
                uncertainty.append({
                    "kind": "unverifiable_withdrawal",
                    "detail": "%s:%s" % (e["identifier"],
                                         e.get("detail", ""))})
            if e.get("changed_fields_unavailable"):
                uncertainty.append({
                    "kind": "changed_fields_unavailable",
                    "detail": "%s:状态方言不存字段,仅知指纹变化"
                              % e["identifier"]})
        if proposal and proposal.get("requires_approval"):
            uncertainty.append({
                "kind": "watermark_unapproved",
                "detail": "水印推进提案 requires_approval=true,"
                          "本技能未写回组织者状态;" +
                          proposal.get("diff_summary", "")})
        if applied:
            for a in applied:
                if a["disposition"] == "escalate":
                    uncertainty.append({
                        "kind": "escalated_pending_human",
                        "detail": "%s:处置为 escalate,待人工线下裁定"
                                  % a["identifier"]})
        if diff.get("baseline_established"):
            uncertainty.append({
                "kind": "baseline_established",
                "detail": "未发现 import_state,本次为首次导入,"
                          "全部当前记录分类为 new"})
        if degraded:
            uncertainty.append({"kind": "sniff_degradation",
                                "detail": degraded})
        if dispositions_pending:
            uncertainty.append({
                "kind": "change_dispositions_pending",
                "detail": "存在待处置的 changed/withdrawn/inconsistent 条目,"
                          "但尚未提供 change_dispositions.json;"
                          "final_governed_state.json 未生成"})
        if selfcheck_report:
            checks = selfcheck_report.get("checks", [])
            if not selfcheck_report.get("ok"):
                uncertainty.append({"kind": "selfcheck_failed",
                                    "detail": "自查未通过,见 checks"})
        if degraded or dispositions_pending \
                or (selfcheck_report and not selfcheck_report.get("ok")):
            status = "partial"
        else:
            status = "success"

    products = {"delta_report": "delta_report.md"
                if os.path.exists(os.path.join(output_dir,
                                               "delta_report.md")) else None,
                "final_governed_state": "final_governed_state.json"
                if os.path.exists(os.path.join(output_dir,
                                               "final_governed_state.json"))
                else None,
                "work_artifacts": {
                    n: n for n in ("previous_state.json", "current_state.json",
                                   "import_diff.json", "sniff_report.json",
                                   "proposed_next_state.json",
                                   "selfcheck.json")
                    if os.path.exists(os.path.join(work_dir, n))}}

    result = {
        "case_id": case["case_id"],
        "skill_name": SKILL_NAME,
        "skill_version": VERSION,
        "status": status,
        "baseline_established": bool(diff and diff.get("baseline_established")),
        "watermark_requires_approval": True,
        "products": products,
        "sources": sources,
        "counts": counts_public,
        "uncertainty": uncertainty,
        "change_records": change_records or [],
        "checks": checks,
        "unresolved_contract_fields": sorted(
            u for u in (unresolved or []) if u),
    }
    for k, v in (contract_values or {}).items():
        result[k] = v
    os.makedirs(output_dir, exist_ok=True)
    write_json(os.path.join(output_dir, "result.json"), result)
    return (0 if status == "success" else 2), {"result": result}


# ---------------------------------------------------------------------------
# selfcheck
# ---------------------------------------------------------------------------

def run_selfcheck(input_dir, work_dir, output_dir):
    checks = []

    def add(name, ok, detail):
        checks.append({"name": name,
                       "status": "PASS" if ok else "FAIL",
                       "detail": detail})

    # 1. result.json 契约键
    req = ["case_id", "skill_name", "status", "products", "sources",
           "uncertainty", "change_records", "counts", "checks",
           "unresolved_contract_fields", "baseline_established",
           "watermark_requires_approval"]
    rpath = os.path.join(output_dir, "result.json")
    if not os.path.exists(rpath):
        add("contract_keys_present", False, "result.json 不存在")
        rep = {"ok": False, "checks": checks}
        write_json(os.path.join(work_dir, "selfcheck.json"), rep)
        return 1, rep
    result = load_json(rpath)
    missing = [k for k in req if k not in result]
    add("contract_keys_present", not missing,
        "缺失:%s" % missing if missing else "全部必需键在场")

    # 2. 分类分区:互不重叠、完备、算术一致
    diff = load_json(os.path.join(work_dir, "import_diff.json"))
    c = diff["counts"]
    total = sum(c[k] for k in CLASSES)
    add("classification_partition",
        total == c["union_size"] == len(diff["entries"]),
        "六类之和 %d = 并集 %d = 条目数 %d" % (total, c["union_size"],
                                              len(diff["entries"])))
    add("counts_arithmetic",
        c["previous_records"] - c["unchanged"] - c["changed"]
        == c["withdrawn"] + c["unverifiable_withdrawal"]
        + c["inconsistent_state"],
        "previous - matched = 未匹配三类之和")

    # 3. 确定性:同输入重跑 parse+diff,import_diff.json 必须字节一致
    det_ok, det_detail = False, ""
    tmp = tempfile.mkdtemp(prefix="ig-selfcheck-")
    try:
        code1, _ = run_parse(input_dir, tmp)
        if code1 in (0,):
            run_diff(tmp)
            p1 = open(os.path.join(tmp, "import_diff.json"), "rb").read()
            p2 = open(os.path.join(work_dir, "import_diff.json"), "rb").read()
            det_ok = (p1 == p2)
            det_detail = ("重跑 import_diff.json 字节一致(%d 字节)"
                          % len(p1) if det_ok else
                          "重跑 import_diff.json 字节不一致!")
        else:
            det_detail = "重跑 parse 返回 %d(降级路径)" % code1
            det_ok = code1 == 2  # 嗅探失败的降级本身也是确定性的
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    add("determinism_rerun", det_ok, det_detail)

    # 4. 水印不回退
    ppath = os.path.join(work_dir, "proposed_next_state.json")
    wm_ok, wm_detail = True, "无数值回归"
    if os.path.exists(ppath):
        proposal = load_json(ppath)
        for db, p in proposal["watermarks"].items():
            if p["action"] == "advance" and p["previous"] and p["proposed"]:
                for k, v in p["proposed"].items():
                    pv = p["previous"].get(k)
                    if isinstance(v, (int, float)) \
                            and isinstance(pv, (int, float)) and v < pv:
                        wm_ok = False
                        wm_detail = "%s.%s 回退:%s→%s" % (db, k, pv, v)
    add("watermark_non_regression", wm_ok, wm_detail)

    # 5. 水印提案未写回(输入 import_state 未被修改)
    previous = load_json(os.path.join(work_dir, "previous_state.json"))
    if previous.get("source_file"):
        src_path = os.path.join(input_dir, previous["source_file"])
        intact = os.path.exists(src_path) and \
            sha256_file(src_path) == previous.get("source_sha256")
        add("input_state_not_modified", intact,
            "输入状态文件 sha256 与解析时一致" if intact
            else "输入状态文件被修改!")
    else:
        add("input_state_not_modified", True, "无输入状态文件(基线模式)")

    # 6. 来源哈希登记
    add("sources_hashed",
        all(s.get("sha256") for s in result.get("sources", [])
            if s["role"] == "material"
            and os.path.exists(os.path.join(input_dir, s["path"]))),
        "全部在场材料已登记 sha256")

    rep = {"ok": all(ch["status"] == "PASS" for ch in checks),
           "checks": checks}
    write_json(os.path.join(work_dir, "selfcheck.json"), rep)
    return (0 if rep["ok"] else 1), rep


# ---------------------------------------------------------------------------
# 脚手架 / run-all
# ---------------------------------------------------------------------------

def scaffold_result(output_dir, case_id=None):
    os.makedirs(output_dir, exist_ok=True)
    skeleton = {
        "case_id": case_id, "skill_name": SKILL_NAME,
        "skill_version": VERSION, "status": "partial",
        "baseline_established": None, "watermark_requires_approval": True,
        "products": {}, "sources": [], "counts": None,
        "uncertainty": [{"kind": "scaffold",
                         "detail": "运行刚开始的诚实 partial 骨架"}],
        "change_records": [], "checks": [],
        "unresolved_contract_fields": [],
    }
    write_json(os.path.join(output_dir, "result.json"), skeleton)


def cmd_run_all(args):
    input_dir, work_dir, output_dir = args.input, args.work, args.output
    # 0. 输入校验 + 骨架
    case, err = load_case(input_dir)
    if err:
        scaffold_result(output_dir)
        result = load_json(os.path.join(output_dir, "result.json"))
        result["status"] = "input_error"
        result["uncertainty"] = [{"kind": "input_error", "detail": err}]
        write_json(os.path.join(output_dir, "result.json"), result)
        sys.stderr.write("[import_governor] input_error: %s\n" % err)
        return 3
    scaffold_result(output_dir, case["case_id"])

    # 1. parse
    code, ctx = run_parse(input_dir, work_dir)
    if code == 3:
        scaffold_result(output_dir)
        return 3
    if code == 2:
        run_finalize(input_dir, work_dir, output_dir,
                     degraded=ctx.get("degraded"))
        sys.stderr.write("[import_governor] partial: %s\n"
                         % ctx.get("degraded"))
        return 2

    # 2. diff
    run_diff(work_dir)
    diff = load_json(os.path.join(work_dir, "import_diff.json"))

    # 3. watermark 提案
    run_watermark(work_dir)

    # 4. 模型处置决定(可选):有待处置条目而无 dispositions → 诚实 partial
    review_pending = [e for e in diff["entries"]
                      if e["class"] in REVIEW_CLASSES]
    applied, change_records = None, []
    dispositions_pending = False
    if review_pending:
        if args.dispositions:
            code, actx = run_apply_dispositions(work_dir, output_dir,
                                                args.dispositions)
            if code != 0:
                run_finalize(input_dir, work_dir, output_dir,
                             degraded=actx.get("error"))
                sys.stderr.write("[import_governor] partial: %s\n"
                                 % actx.get("error"))
                return 2
            applied, change_records = actx["applied"], \
                actx["change_records"]
        else:
            dispositions_pending = True
    else:
        # 无待处置条目(如纯基线):仍可折叠出治理状态
        code, actx = run_apply_dispositions(
            work_dir, output_dir,
            args.dispositions) if args.dispositions else (0, None)
        if actx:
            applied, change_records = actx["applied"], \
                actx["change_records"]

    # 5. report
    run_report(work_dir, output_dir, applied=applied)

    # 6. finalize(先不带自查,再自查后刷新)
    run_finalize(input_dir, work_dir, output_dir,
                 dispositions_pending=dispositions_pending,
                 applied=applied, change_records=change_records)
    sc_code, sc_rep = run_selfcheck(input_dir, work_dir, output_dir)
    code, _ = run_finalize(input_dir, work_dir, output_dir,
                           dispositions_pending=dispositions_pending,
                           selfcheck_report=sc_rep,
                           applied=applied, change_records=change_records)
    # report 需包含 dispositions 表,已在上一步 applied 下生成
    if sc_code != 0:
        return 2
    return code


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser():
    p = argparse.ArgumentParser(
        prog=TOOL_NAME,
        description="增量导入治理与变更追踪:对账 import_state × 当前离线响应,"
                    "六路分类 + 水印推进提案(需批准,绝不静默写回)。"
                    "退出码 0=success,2=partial,3=input_error。")
    sub = p.add_subparsers(dest="command")

    def common(sp, need_output=False):
        sp.add_argument("--input", default="/input",
                        help="输入目录(含 case.json/task.md/materials)")
        sp.add_argument("--work", default="/app/work", help="工作目录")
        if need_output:
            sp.add_argument("--output", default="/app/output",
                            help="输出目录")

    sp = sub.add_parser("parse", help="嗅探材料 + 生成 previous/current 状态")
    common(sp)
    sp = sub.add_parser("diff", help="六路分类对账 → import_diff.json")
    common(sp)
    sp = sub.add_parser("watermark", help="水印推进提案 → proposed_next_state.json")
    common(sp)
    sp = sub.add_parser("report", help="生成 delta_report.md")
    common(sp, need_output=True)
    sp = sub.add_parser("apply-dispositions",
                        help="折叠模型处置 → final_governed_state.json")
    common(sp, need_output=True)
    sp.add_argument("--dispositions", required=True,
                    help="change_dispositions.json 路径")
    sp = sub.add_parser("finalize", help="生成/刷新 result.json")
    common(sp, need_output=True)
    sp = sub.add_parser("selfcheck", help="契约/分区/确定性/回归自查")
    common(sp, need_output=True)
    sp = sub.add_parser("run-all", help="全流程(诚实降级)")
    common(sp, need_output=True)
    sp.add_argument("--dispositions", default=None,
                    help="可选:模型 change_dispositions.json 路径")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    if not args.command:
        build_parser().print_help()
        return 0
    if args.command == "parse":
        code, ctx = run_parse(args.input, args.work)
        if code == 3:
            sys.stderr.write("[import_governor] input_error: %s\n"
                             % ctx.get("error"))
        elif code == 2:
            sys.stderr.write("[import_governor] partial: %s\n"
                             % ctx.get("degraded"))
        return code
    if args.command == "diff":
        code, _ = run_diff(args.work)
        return code
    if args.command == "watermark":
        code, _ = run_watermark(args.work)
        return code
    if args.command == "report":
        code, _ = run_report(args.work, args.output)
        return code
    if args.command == "apply-dispositions":
        code, ctx = run_apply_dispositions(args.work, args.output,
                                           args.dispositions)
        if code != 0:
            sys.stderr.write("[import_governor] %s: %s\n"
                             % (ctx.get("error"),
                                ctx.get("details", "")))
        return code
    if args.command == "finalize":
        code, _ = run_finalize(args.input, args.work, args.output)
        return code
    if args.command == "selfcheck":
        code, rep = run_selfcheck(args.input, args.work, args.output)
        for ch in rep["checks"]:
            sys.stdout.write("[%s] %s — %s\n" % (ch["status"], ch["name"],
                                                 ch["detail"]))
        return code
    if args.command == "run-all":
        return cmd_run_all(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
