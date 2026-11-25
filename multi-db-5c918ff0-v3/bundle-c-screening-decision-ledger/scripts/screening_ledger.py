#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
screening_ledger.py — 筛选判定账本（screening decision ledger）.

离线多数据库联合检索场景下的纳入/排除判定层：把 task.md 编译出的资格标准
（criteria.json，模型职责）与逐记录判定（judgments.json，模型职责）落到一份
可审计的判定账本上，并由账本行**重算** PRISMA 风格流量计数，而不是断言计数。

子命令（全部 Python 3 标准库实现，无网络、无随机性、产物不含墙钟时间）：

  parse               嗅探+规范化 crossref / europepmc / publisher(JSON/JSONL/CSV)
                      材料；按规范化 DOI，再按规范化标题+年份+第一作者姓氏做最小
                      去重（仅用于喂流量计数）；写 normalized.jsonl + dedup_summary.json
  prescreen           应用 criteria.json 中的机器可判标准（publication_year 范围、
                      document_type 排除），写 prescreen_decisions.jsonl
  validate-judgments  严格校验 judgments.json：schema、decision 枚举、criterion id
                      必须存在于 criteria.json、evidence_quote 必须是该记录
                      标题/摘要的逐珠子串（伪造引用 → 详细报错，退出 3）
  ledger              合并 prescreen + 判定 + 边界裁定 → decision_ledger.jsonl
                      （每记录一行，逻辑序号，无时间戳）；未决边界 → borderline_queue.json
  flow                从账本行**逐条计数**出 prisma_flow.json，断言守恒不变量，
                      渲染 prisma_flow.md 文本流程表
  report              生成 screening_report.md（标准表含 task.md 原文引用、纳入清单
                      含理由、排除原因矩阵、边界裁定、局限）
  finalize            candidate_set.json（模型 rank 否则稳定序）+ result.json
                      （case_id + 全部 output_contract 字段，无法填充→null+unresolved，
                      来源 sha256，uncertainty，change_records，counts，checks）
  selfcheck           契约键、守恒、每条 exclude ≥1 标准、引用逐珠核验、计数重算；
                      退出 0/1
  run-all             顺序串联以上各步，诚实降级（缺 criteria → 先写骨架再退出 2）

退出码：0 成功 | 2 诚实降级（partial） | 3 输入无效（selfcheck 用 0/1）。
"""

import argparse
import csv
import hashlib
import html
import json
import os
import re
import sys
import unicodedata

VERSION = "1.0.0"
SKILL_NAME = "screening-decision-ledger"

SOURCE_PRIORITY = ["publisher", "crossref", "europepmc"]

DECISIONS = ("include", "exclude", "borderline")
STAGES = ("prescreen", "screen", "borderline_resolution")

INSUFFICIENT = "insufficient_evidence"

# output_contract 字段名 → 填充来源的子串映射（无法匹配的一律 null + unresolved）
CONTRACT_FILLERS = [
    (("candidate_set", "candidates", "included_records", "included"), "candidate_set"),
    (("prisma_flow", "flow_counts", "flow"), "prisma_flow"),
    (("exclusion_reasons", "exclusions", "excluded"), "exclusion_reasons"),
    (("screening_criteria", "eligibility_criteria", "criteria"), "criteria"),
    (("borderline",), "borderline_resolutions"),
    (("screening_report", "report"), "screening_report_path"),
]


class InvalidInput(Exception):
    """结构性无效输入（退出 3）。"""


class DegradedRun(Exception):
    """诚实降级（退出 2）。"""


# ---------------------------------------------------------------------------
# 通用工具
# ---------------------------------------------------------------------------

def read_json(path, what):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        raise InvalidInput("%s 不存在: %s" % (what, path))
    except json.JSONDecodeError as exc:
        raise InvalidInput("%s 不是合法 JSON: %s (%s)" % (what, path, exc))


def write_json(path, obj):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")


def write_text(path, text):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def read_jsonl(path):
    rows = []
    if not os.path.exists(path):
        return rows
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def write_jsonl(path, rows):
    with open(path, "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def sha256_of(path):
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)


# ---------------------------------------------------------------------------
# 规范化
# ---------------------------------------------------------------------------

def strip_html(value):
    return re.sub(r"<[^>]+>", " ", value)


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


def clean_text(value):
    """标题/摘要的展示形态：NFC + 去 HTML + 折叠空白（不改写内容字符）。"""
    if not isinstance(value, str):
        return None
    v = unicodedata.normalize("NFC", value)
    v = html.unescape(v)
    v = strip_html(v)
    v = re.sub(r"\s+", " ", v).strip()
    return v or None


def norm_surname(value):
    if not isinstance(value, str):
        return None
    v = unicodedata.normalize("NFC", value).strip().lower()
    v = re.sub(r"[^\w\-]", "", v, flags=re.UNICODE)
    return v or None


def first_surname_from_author_string(author_string):
    """EuropePMC authorString 'Li N, Smith J' → 'li'；'Zhang, Wei' → 'zhang'。"""
    if not isinstance(author_string, str) or not author_string.strip():
        return None
    first = author_string.split(",")[0].strip()
    token = first.split()[0] if first.split() else ""
    return norm_surname(token)


def first_surname_from_name(name):
    """出版方作者 'Wei Zhang' → 'zhang'；'Zhang, Wei' → 'zhang'。"""
    if not isinstance(name, str) or not name.strip():
        return None
    if "," in name:
        return norm_surname(name.split(",")[0])
    parts = name.split()
    return norm_surname(parts[-1]) if parts else None


def to_int(value):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# parse：材料嗅探与记录规范化
# ---------------------------------------------------------------------------

def sniff_material(path):
    """返回 (kind, payload)。kind ∈ crossref|europepmc|publisher|reference_graph|
    import_state|unknown。绝不强解无法识别形状的材料。"""
    lower = os.path.basename(path).lower()
    if lower.endswith(".csv"):
        with open(path, "r", encoding="utf-8-sig", newline="") as fh:
            rows = list(csv.DictReader(fh))
        if rows and any(k and "title" in k.lower() for k in rows[0].keys()):
            return "publisher", {"format": "csv", "rows": rows}
        return "unknown", {"reason": "csv_without_title_column"}
    raw = None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
    except (OSError, UnicodeDecodeError) as exc:
        return "unknown", {"reason": "unreadable: %s" % exc}
    stripped = text.strip()
    if not stripped:
        return "unknown", {"reason": "empty_file"}
    try:
        raw = json.loads(stripped)
    except json.JSONDecodeError:
        # JSONL 尝试
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
            return "publisher", {"format": "jsonl", "rows": rows}
        return "unknown", {"reason": "not_json_not_jsonl"}
    if isinstance(raw, dict):
        msg = raw.get("message")
        if isinstance(msg, dict) and isinstance(msg.get("items"), list):
            return "crossref", {"format": "json", "items": msg["items"]}
        rl = raw.get("resultList")
        if isinstance(rl, dict) and isinstance(rl.get("result"), list):
            return "europepmc", {"format": "json", "items": rl["result"]}
        if isinstance(raw.get("aliases"), (list, dict)) or isinstance(
                raw.get("known_aliases"), (list, dict)):
            return "reference_graph", {"format": "json"}
        if isinstance(raw.get("imported_ids"), (list, dict)) or isinstance(
                raw.get("last_import"), (str, dict)) or "import_state" in lower:
            return "import_state", {"format": "json"}
        if "reference_graph" in lower:
            return "reference_graph", {"format": "json"}
        return "unknown", {"reason": "unrecognized_json_object"}
    if isinstance(raw, list):
        if all(isinstance(r, dict) for r in raw):
            return "publisher", {"format": "json", "items": raw}
        return "unknown", {"reason": "json_array_of_non_objects"}
    return "unknown", {"reason": "unexpected_json_type"}


def normalize_crossref(item):
    title = None
    if isinstance(item.get("title"), list) and item["title"]:
        title = clean_text(item["title"][0])
    authors = []
    for a in item.get("author") or []:
        if isinstance(a, dict):
            family = a.get("family")
            given = a.get("given")
            if family:
                authors.append(("%s %s" % (given, family)).strip() if given else family)
    surname = None
    if item.get("author") and isinstance(item["author"][0], dict):
        surname = norm_surname(item["author"][0].get("family"))
    year = None
    issued = item.get("issued")
    if isinstance(issued, dict):
        dp = issued.get("date-parts")
        if isinstance(dp, list) and dp and isinstance(dp[0], list) and dp[0]:
            year = to_int(dp[0][0])
    journal = None
    if isinstance(item.get("container-title"), list) and item["container-title"]:
        journal = clean_text(item["container-title"][0])
    return {
        "doi": norm_doi(item.get("DOI")),
        "pmid": None,
        "title": title,
        "abstract": clean_text(item.get("abstract")),
        "year": year,
        "authors": authors,
        "first_author_surname": surname,
        "journal": journal,
        "doc_type": clean_text(item.get("type")),
        "url": item.get("URL") if isinstance(item.get("URL"), str) else None,
    }


def normalize_europepmc(item):
    authors = []
    if isinstance(item.get("authorString"), str):
        authors = [a.strip() for a in item["authorString"].split(",") if a.strip()]
    doc_type = None
    ptl = item.get("pubTypeList")
    if isinstance(ptl, dict) and isinstance(ptl.get("pubType"), list) and ptl["pubType"]:
        doc_type = clean_text(str(ptl["pubType"][0]))
    pmid = item.get("pmid") or item.get("id")
    return {
        "doi": norm_doi(item.get("doi")),
        "pmid": str(pmid) if pmid is not None else None,
        "title": clean_text(item.get("title")),
        "abstract": clean_text(item.get("abstractText")),
        "year": to_int(item.get("pubYear")),
        "authors": authors,
        "first_author_surname": first_surname_from_author_string(
            item.get("authorString")),
        "journal": clean_text(item.get("journalTitle")),
        "doc_type": doc_type,
        "url": None,
    }


def normalize_publisher(item):
    raw_authors = item.get("authors") or item.get("author") or []
    if isinstance(raw_authors, str):
        raw_authors = [raw_authors]
    authors = [a for a in raw_authors if isinstance(a, str)]
    surname = first_surname_from_name(authors[0]) if authors else None
    year = to_int(item.get("year") or item.get("publication_year")
                  or item.get("published"))
    doc_type = (item.get("article_type") or item.get("doc_type")
                or item.get("type"))
    return {
        "doi": norm_doi(item.get("doi") or item.get("DOI")),
        "pmid": str(item["pmid"]) if item.get("pmid") is not None else None,
        "title": clean_text(item.get("title")),
        "abstract": clean_text(item.get("abstract")),
        "year": year,
        "authors": authors,
        "first_author_surname": surname,
        "journal": clean_text(item.get("journal")),
        "doc_type": clean_text(doc_type),
        "url": item.get("url") if isinstance(item.get("url"), str) else None,
    }


NORMALIZERS = {
    "crossref": normalize_crossref,
    "europepmc": normalize_europepmc,
    "publisher": normalize_publisher,
}


def record_priority(source):
    try:
        return SOURCE_PRIORITY.index(source)
    except ValueError:
        return len(SOURCE_PRIORITY)


def dedup_key_biblio(rec):
    if rec.get("title") and rec.get("year") and rec.get("first_author_surname"):
        return (norm_title(rec["title"]), rec["year"],
                rec["first_author_surname"])
    return None


def cmd_parse(args):
    input_dir = args.input
    work_dir = args.work
    ensure_dir(work_dir)

    case_path = os.path.join(input_dir, "case.json")
    if not os.path.exists(case_path):
        raise InvalidInput("case.json 缺失: %s（无法确定 case_id 与材料清单）"
                           % case_path)
    case = read_json(case_path, "case.json")
    if not isinstance(case, dict) or not case.get("case_id"):
        raise InvalidInput("case.json 缺少 case_id: %s" % case_path)

    task_path = os.path.join(input_dir, "task.md")
    task_text = ""
    if os.path.exists(task_path):
        with open(task_path, "r", encoding="utf-8") as fh:
            task_text = fh.read()

    material_rels = case.get("materials")
    if not isinstance(material_rels, list) or not material_rels:
        # 回退：扫描 input_dir/materials 下所有文件（排序保证确定性）
        mdir = os.path.join(input_dir, "materials")
        material_rels = []
        if os.path.isdir(mdir):
            for name in sorted(os.listdir(mdir)):
                if os.path.isfile(os.path.join(mdir, name)):
                    material_rels.append("materials/" + name)

    raw_records = []        # 每条原始记录：含 _source/_locator/_seq
    sources_manifest = []   # 材料清单（含 sha256）
    quarantined = []
    identified_per_source = {}
    seq = 0
    for rel in sorted(material_rels):
        path = os.path.join(input_dir, rel)
        if not os.path.exists(path):
            quarantined.append({"material": rel, "reason": "file_missing"})
            continue
        kind, payload = sniff_material(path)
        entry = {"material": rel, "kind": kind, "sha256": sha256_of(path)}
        if kind in NORMALIZERS:
            items = payload.get("items") or payload.get("rows") or []
            entry["records"] = len(items)
            identified_per_source[kind] = identified_per_source.get(kind, 0) + len(items)
            for idx, item in enumerate(items):
                seq += 1
                rec = NORMALIZERS[kind](item)
                rec["_seq"] = seq
                rec["_source"] = kind
                rec["_locator"] = "%s#%d" % (rel, idx)
                rec["_material"] = rel
                raw_records.append(rec)
        else:
            entry["records"] = 0
            if kind == "unknown":
                quarantined.append({"material": rel,
                                    "reason": payload.get("reason", "unknown")})
        sources_manifest.append(entry)

    # 赋原始记录 id（扫描序）
    for i, rec in enumerate(raw_records, 1):
        rec["raw_id"] = "raw-%04d" % i

    # 最小去重：先按规范化 DOI 精确，再按 规范化标题+年份+第一作者姓氏
    canonical = []
    dup_groups = []
    for rec in raw_records:  # raw_records 已按确定顺序
        hit = None
        match_kind = None
        for canon in canonical:
            if rec.get("doi") and canon.get("doi") and rec["doi"] == canon["doi"]:
                hit, match_kind = canon, "doi"
                break
            ka, kb = dedup_key_biblio(rec), dedup_key_biblio(canon)
            if ka and kb and ka == kb:
                hit, match_kind = canon, "bibliographic"
                break
        if hit is None:
            canon = dict(rec)
            canon["sources"] = [rec["_source"]]
            canon["member_ids"] = [rec["raw_id"]]
            canon["locators"] = [rec["_locator"]]
            canonical.append(canon)
        else:
            group = {"kept": None, "absorbed": rec["raw_id"],
                     "match": match_kind,
                     "kept_source": hit["_source"],
                     "absorbed_source": rec["_source"]}
            if record_priority(rec["_source"]) < record_priority(hit["_source"]):
                # 更高优先级来源胜出，保留低优先来源的标识符补丁
                old_id = hit["raw_id"]
                old_src = hit["_source"]
                old_loc = hit["_locator"]
                merged = dict(rec)
                merged["sources"] = [rec["_source"]] + hit["sources"]
                merged["member_ids"] = [rec["raw_id"]] + hit["member_ids"]
                merged["locators"] = [rec["_locator"]] + hit["locators"]
                for key in ("doi", "pmid", "title", "abstract", "year",
                            "authors", "first_author_surname", "journal",
                            "doc_type", "url"):
                    if not merged.get(key) and hit.get(key):
                        merged[key] = hit[key]
                if not merged.get("pmid") and hit.get("pmid"):
                    merged["pmid"] = hit["pmid"]
                merged["raw_id"] = old_id  # 保持稳定 record_id
                idx = canonical.index(hit)
                canonical[idx] = merged
                group["kept"] = old_id
                group["kept_source"] = rec["_source"]
                group["note"] = ("higher-priority source %s replaced %s"
                                 % (rec["_source"], old_src))
            else:
                if rec["_source"] not in hit["sources"]:
                    hit["sources"].append(rec["_source"])
                hit["member_ids"].append(rec["raw_id"])
                hit["locators"].append(rec["_locator"])
                if not hit.get("pmid") and rec.get("pmid"):
                    hit["pmid"] = rec["pmid"]
                if not hit.get("doi") and rec.get("doi"):
                    hit["doi"] = rec["doi"]
                group["kept"] = hit["raw_id"]
            dup_groups.append(group)

    # 规范记录 id 与稳定排序
    canonical.sort(key=lambda r: r["_seq"])
    out_records = []
    for i, canon in enumerate(canonical, 1):
        rid = "rec-%04d" % i
        out = {
            "record_id": rid,
            "source": canon["_source"],
            "sources": sorted(canon["sources"]),
            "member_ids": canon["member_ids"],
            "locators": sorted(canon["locators"]),
            "doi": canon.get("doi"),
            "pmid": canon.get("pmid"),
            "title": canon.get("title"),
            "abstract": canon.get("abstract"),
            "year": canon.get("year"),
            "authors": canon.get("authors") or [],
            "first_author_surname": canon.get("first_author_surname"),
            "journal": canon.get("journal"),
            "doc_type": canon.get("doc_type"),
            "url": canon.get("url"),
            "has_abstract": bool(canon.get("abstract")),
        }
        out_records.append(out)
    for g in dup_groups:
        # kept 指向的是 raw_id；映射到规范 record_id
        for canon, out in zip(canonical, out_records):
            if g["kept"] in canon["member_ids"] or g["kept"] == canon["raw_id"]:
                g["kept_record_id"] = out["record_id"]
                break

    write_jsonl(os.path.join(work_dir, "normalized.jsonl"), out_records)
    dedup_summary = {
        "identified_per_source": identified_per_source,
        "total_identified": len(raw_records),
        "duplicates_removed": len(raw_records) - len(out_records),
        "duplicate_groups": dup_groups,
        "canonical_records": len(out_records),
        "quarantined_materials": quarantined,
        "sources_manifest": sources_manifest,
        "note": ("去重仅用于喂流量计数：规范化 DOI 精确匹配优先，"
                 "否则规范化标题+年份+第一作者姓氏全同；不做模糊合并。"),
    }
    write_json(os.path.join(work_dir, "dedup_summary.json"), dedup_summary)
    # 供后续步骤使用
    write_json(os.path.join(work_dir, "case_echo.json"), {
        "case_id": case["case_id"],
        "output_contract": case.get("output_contract") or {},
        "research_question": case.get("research_question"),
        "task_md_present": bool(task_text.strip()),
        "task_md_path": "task.md" if task_text.strip() else None,
    })
    if task_text.strip():
        write_text(os.path.join(work_dir, "task_copy.md"), task_text)
    print("parse: %d raw records -> %d canonical (%d duplicates removed), "
          "%d quarantined material(s)"
          % (len(raw_records), len(out_records),
             len(raw_records) - len(out_records), len(quarantined)))
    return 0


# ---------------------------------------------------------------------------
# criteria 读取与校验
# ---------------------------------------------------------------------------

def load_criteria(path, required=True):
    if not path or not os.path.exists(path):
        if required:
            raise InvalidInput("criteria 文件缺失: %s" % path)
        return None
    data = read_json(path, "criteria.json")
    if isinstance(data, dict) and isinstance(data.get("criteria"), list):
        items = data["criteria"]
    elif isinstance(data, list):
        items = data
    else:
        raise InvalidInput("criteria.json 形状非法：应为列表或含 criteria 列表的对象")
    seen = set()
    for c in items:
        if not isinstance(c, dict):
            raise InvalidInput("criteria.json 含非对象条目")
        for key in ("id", "kind", "definition", "source_quote"):
            if not c.get(key):
                raise InvalidInput("criterion 缺少字段 %s: %r" % (key, c))
        if c["kind"] not in ("inclusion", "exclusion"):
            raise InvalidInput("criterion %s kind 非法: %r" % (c["id"], c["kind"]))
        if c["id"] in seen:
            raise InvalidInput("criterion id 重复: %s" % c["id"])
        seen.add(c["id"])
    return {"criteria": items,
            "derived_needs_confirmation":
                bool(isinstance(data, dict)
                     and data.get("derived_needs_confirmation"))}


def machine_check(criterion, record):
    """返回 (applicable, failed, evidence)。仅 exclusion 且带 machine 块的标准
    可被脚本预判。字段缺失 → applicable=False（不自动排除）。"""
    machine = criterion.get("machine")
    if criterion.get("kind") != "exclusion" or not isinstance(machine, dict):
        return False, False, None
    mtype = machine.get("type")
    if mtype == "year_range":
        year = record.get("year")
        if year is None:
            return False, False, None
        ymin, ymax = machine.get("min"), machine.get("max")
        failed = ((ymin is not None and year < ymin)
                  or (ymax is not None and year > ymax))
        ev = "year=%s, required range [%s, %s]" % (year, ymin, ymax)
        return True, failed, ev
    if mtype == "document_type":
        dt = record.get("doc_type")
        if not dt:
            return False, False, None
        low = dt.lower()
        for bad in machine.get("exclude_types") or []:
            if isinstance(bad, str) and bad.lower() in low:
                return True, True, "doc_type=%r matches exclude_types entry %r" % (
                    dt, bad)
        return True, False, "doc_type=%r not in exclude_types" % dt
    return False, False, None


def cmd_prescreen(args):
    work_dir = args.work
    records = read_jsonl(os.path.join(work_dir, "normalized.jsonl"))
    if not records:
        raise InvalidInput("normalized.jsonl 为空或缺失，请先运行 parse")
    crit = load_criteria(args.criteria)
    decisions = []
    pending = []
    for rec in records:
        decided = False
        for c in crit["criteria"]:
            applicable, failed, evidence = machine_check(c, rec)
            if applicable and failed:
                decisions.append({
                    "record_id": rec["record_id"],
                    "stage": "prescreen",
                    "decision": "exclude",
                    "criterion_ids": [c["id"]],
                    "evidence": evidence,
                    "evidence_kind": "field",
                    "decided_by": "script",
                })
                decided = True
                break  # 一个机器排除理由足够；其余标准仍可由模型补充说明
        if not decided:
            pending.append(rec["record_id"])
    write_jsonl(os.path.join(work_dir, "prescreen_decisions.jsonl"), decisions)
    write_json(os.path.join(work_dir, "prescreen_pending.json"),
               {"pending_record_ids": pending,
                "auto_excluded": len(decisions),
                "note": "pending 记录需模型判定（judgments.json）"})
    print("prescreen: %d auto-excluded, %d pending for model judgment"
          % (len(decisions), len(pending)))
    return 0


# ---------------------------------------------------------------------------
# judgments 校验
# ---------------------------------------------------------------------------

def record_text_blob(record):
    parts = []
    if record.get("title"):
        parts.append(record["title"])
    if record.get("abstract"):
        parts.append(record["abstract"])
    return "\n".join(parts)


def validate_judgments_obj(judgments, criteria, records_by_id, judgments_path):
    """返回 (errors, validated)。严格模式：任何错误 → 退出 3。"""
    errors = []
    validated = []
    crit_ids = {c["id"] for c in criteria["criteria"]}
    if not isinstance(judgments, list):
        return ["judgments 必须是 JSON 数组: %s" % judgments_path], []
    seen_records = set()
    for i, j in enumerate(judgments):
        where = "judgments[%d]" % i
        if not isinstance(j, dict):
            errors.append("%s 不是对象" % where)
            continue
        rid = j.get("record_id")
        if not isinstance(rid, str) or not rid:
            errors.append("%s 缺少 record_id" % where)
            continue
        if rid not in records_by_id:
            errors.append("%s record_id %r 不在 normalized.jsonl 中" % (where, rid))
            continue
        if rid in seen_records:
            errors.append("%s record_id %r 重复判定" % (where, rid))
            continue
        seen_records.add(rid)
        decision = j.get("decision")
        if decision not in DECISIONS:
            errors.append("%s decision %r 非法，必须为 include|exclude|borderline"
                          % (where, decision))
            continue
        cids = j.get("criterion_ids")
        if decision in ("include", "exclude"):
            if not isinstance(cids, list) or not cids:
                errors.append("%s %s 判定必须引用至少一个 criterion id"
                              % (where, decision))
                continue
        else:
            cids = cids if isinstance(cids, list) else []
        unknown = [c for c in cids if c not in crit_ids]
        if unknown:
            errors.append("%s 引用了 criteria.json 中不存在的 criterion id: %s"
                          % (where, ", ".join(sorted(unknown))))
            continue
        quote = j.get("evidence_quote")
        status = j.get("evidence_status")
        blob = record_text_blob(records_by_id[rid])
        if status == INSUFFICIENT:
            if decision != "borderline":
                errors.append("%s evidence_status=%s 仅允许用于 borderline 判定；"
                              "include/exclude 必须给出逐字 evidence_quote"
                              % (where, INSUFFICIENT))
                continue
        else:
            if not isinstance(quote, str) or not quote.strip():
                errors.append("%s 缺少 evidence_quote（或显式 evidence_status=%s）"
                              % (where, INSUFFICIENT))
                continue
            if quote not in blob:
                errors.append(
                    "%s evidence_quote 不是记录 %s 标题/摘要的逐珠子串。"
                    " 判定纪律禁止臆造证据。quote=%r"
                    % (where, rid, quote[:120]))
                continue
        rank = j.get("rank")
        if rank is not None and not isinstance(rank, int):
            errors.append("%s rank 必须为整数" % where)
            continue
        validated.append({
            "record_id": rid,
            "decision": decision,
            "criterion_ids": cids,
            "evidence_quote": quote if status != INSUFFICIENT else None,
            "evidence_status": status if status == INSUFFICIENT else "verbatim",
            "basis": j.get("basis") or (
                "title-only" if not records_by_id[rid].get("has_abstract")
                else "title+abstract"),
            "rank": rank,
            "rationale": j.get("rationale"),
        })
    return errors, validated


def cmd_validate_judgments(args):
    work_dir = args.work
    records = read_jsonl(os.path.join(work_dir, "normalized.jsonl"))
    if not records:
        raise InvalidInput("normalized.jsonl 为空或缺失，请先运行 parse")
    records_by_id = {r["record_id"]: r for r in records}
    criteria = load_criteria(args.criteria)
    judgments = read_json(args.judgments, "judgments.json")
    errors, validated = validate_judgments_obj(
        judgments, criteria, records_by_id, args.judgments)
    if errors:
        for e in errors:
            print("VALIDATION ERROR: %s" % e, file=sys.stderr)
        print("validate-judgments: %d 处错误，判定文件被拒绝" % len(errors),
              file=sys.stderr)
        return 3
    write_json(os.path.join(work_dir, "judgments.validated.json"), validated)
    print("validate-judgments: %d 条判定全部通过校验" % len(validated))
    return 0


# ---------------------------------------------------------------------------
# ledger
# ---------------------------------------------------------------------------

def cmd_ledger(args):
    work_dir = args.work
    records = read_jsonl(os.path.join(work_dir, "normalized.jsonl"))
    if not records:
        raise InvalidInput("normalized.jsonl 为空或缺失，请先运行 parse")
    records_by_id = {r["record_id"]: r for r in records}
    criteria = load_criteria(args.criteria)
    prescreen = read_jsonl(os.path.join(work_dir, "prescreen_decisions.jsonl"))
    prescreen_by_id = {d["record_id"]: d for d in prescreen}

    validated_path = os.path.join(work_dir, "judgments.validated.json")
    if args.judgments:
        # 就地再校验一次（防止绕过 validate-judgments）
        judgments = read_json(args.judgments, "judgments.json")
        errors, validated = validate_judgments_obj(
            judgments, criteria, records_by_id, args.judgments)
        if errors:
            for e in errors:
                print("VALIDATION ERROR: %s" % e, file=sys.stderr)
            return 3
        write_json(validated_path, validated)
    elif os.path.exists(validated_path):
        validated = read_json(validated_path, "judgments.validated.json")
    else:
        validated = []
    judgments_by_id = {j["record_id"]: j for j in validated}

    borderline_decisions = {}
    if args.borderline_decisions and os.path.exists(args.borderline_decisions):
        bd = read_json(args.borderline_decisions, "borderline_decisions.json")
        if not isinstance(bd, list):
            raise InvalidInput("borderline_decisions.json 必须是数组")
        for i, b in enumerate(bd):
            where = "borderline_decisions[%d]" % i
            if not isinstance(b, dict) or b.get("decision") not in ("include",
                                                                    "exclude"):
                raise InvalidInput("%s 缺少合法 decision(include|exclude)" % where)
            rid = b.get("record_id")
            if rid not in records_by_id:
                raise InvalidInput("%s record_id %r 未知" % (where, rid))
            cids = b.get("criterion_ids") or []
            crit_ids = {c["id"] for c in criteria["criteria"]}
            unknown = [c for c in cids if c not in crit_ids]
            if unknown:
                raise InvalidInput("%s 未知 criterion id: %s"
                                   % (where, ", ".join(sorted(unknown))))
            quote = b.get("evidence_quote")
            blob = record_text_blob(records_by_id[rid])
            if not isinstance(quote, str) or quote not in blob:
                raise InvalidInput(
                    "%s evidence_quote 不是记录 %s 标题/摘要的逐珠子串"
                    % (where, rid))
            borderline_decisions[rid] = b

    ledger_rows = []
    pending_borderline = []
    unjudged = []
    seq = 0
    for rec in records:
        rid = rec["record_id"]
        if rid in prescreen_by_id:
            d = prescreen_by_id[rid]
            seq += 1
            ledger_rows.append({
                "seq": seq, "record_id": rid, "stage": "prescreen",
                "decision": "exclude", "criterion_ids": d["criterion_ids"],
                "evidence": d["evidence"], "evidence_kind": "field",
                "decided_by": "script",
            })
            continue
        j = judgments_by_id.get(rid)
        if j is None:
            unjudged.append(rid)
            continue
        if j["decision"] in ("include", "exclude"):
            seq += 1
            ledger_rows.append({
                "seq": seq, "record_id": rid, "stage": "screen",
                "decision": j["decision"], "criterion_ids": j["criterion_ids"],
                "evidence": j["evidence_quote"], "evidence_kind": "quote",
                "basis": j["basis"], "decided_by": "model",
                "rationale": j.get("rationale"),
                "rank": j.get("rank"),
            })
        else:  # borderline
            b = borderline_decisions.get(rid)
            if b is not None:
                seq += 1
                ledger_rows.append({
                    "seq": seq, "record_id": rid,
                    "stage": "borderline_resolution",
                    "decision": b["decision"],
                    "criterion_ids": b.get("criterion_ids") or [],
                    "evidence": b["evidence_quote"], "evidence_kind": "quote",
                    "decided_by": "model",
                    "rationale": b.get("rationale"),
                    "rank": b.get("rank"),
                    "initial_judgment": "borderline",
                })
            else:
                seq += 1
                ledger_rows.append({
                    "seq": seq, "record_id": rid, "stage": "screen",
                    "decision": "borderline",
                    "criterion_ids": j["criterion_ids"],
                    "evidence": j["evidence_quote"],
                    "evidence_kind": ("quote" if j["evidence_quote"]
                                      else "insufficient_evidence"),
                    "basis": j["basis"], "decided_by": "model",
                    "rationale": j.get("rationale"),
                })
                pending_borderline.append(rid)

    write_jsonl(os.path.join(work_dir, "decision_ledger.jsonl"), ledger_rows)
    write_json(os.path.join(work_dir, "borderline_queue.json"), {
        "pending": sorted(pending_borderline),
        "unjudged": sorted(unjudged),
        "resolved": sorted(borderline_decisions.keys()),
        "note": ("pending=判为 borderline 但尚无裁定；unjudged=无任何判定；"
                 "两者存在时 finalize 的 status 必为 partial"),
    })
    print("ledger: %d ledger rows, %d borderline pending, %d unjudged"
          % (len(ledger_rows), len(pending_borderline), len(unjudged)))
    return 0


# ---------------------------------------------------------------------------
# flow：由账本行重算的 PRISMA 风格流量
# ---------------------------------------------------------------------------

def compute_flow(work_dir):
    dedup = read_json(os.path.join(work_dir, "dedup_summary.json"),
                      "dedup_summary.json")
    ledger = read_jsonl(os.path.join(work_dir, "decision_ledger.jsonl"))
    records = read_jsonl(os.path.join(work_dir, "normalized.jsonl"))
    queue = read_json(os.path.join(work_dir, "borderline_queue.json"),
                      "borderline_queue.json") if os.path.exists(
        os.path.join(work_dir, "borderline_queue.json")) else {
        "pending": [], "unjudged": []}

    identified = dedup["total_identified"]
    dups = dedup["duplicates_removed"]
    screened = len(ledger)
    excluded_rows = [r for r in ledger if r["decision"] == "exclude"]
    included_rows = [r for r in ledger if r["decision"] == "include"]
    pending_rows = [r for r in ledger if r["decision"] == "borderline"]
    unjudged = len(records) - screened

    per_criterion = {}
    for r in excluded_rows:
        for cid in r["criterion_ids"]:
            per_criterion[cid] = per_criterion.get(cid, 0) + 1

    checks = []
    c1 = identified - dups == len(records)
    checks.append({"invariant": "identified - duplicates_removed == canonical_records",
                   "lhs": identified - dups, "rhs": len(records), "ok": c1})
    c2 = screened + unjudged == len(records)
    checks.append({"invariant": "records_screened + unjudged == canonical_records",
                   "lhs": screened + unjudged, "rhs": len(records), "ok": c2})
    c3 = (len(excluded_rows) + len(included_rows) + len(pending_rows)
          == screened)
    checks.append({"invariant": "excluded + included + borderline_pending "
                                "== records_screened",
                   "lhs": len(excluded_rows) + len(included_rows)
                          + len(pending_rows),
                   "rhs": screened, "ok": c3})

    flow = {
        "records_identified": {
            "per_source": dedup["identified_per_source"],
            "total": identified,
        },
        "duplicates_removed": dups,
        "records_screened": screened,
        "records_unjudged": unjudged,
        "records_excluded": {
            "total": len(excluded_rows),
            "per_criterion": per_criterion,
            "per_stage": {
                "prescreen_script":
                    sum(1 for r in excluded_rows if r["stage"] == "prescreen"),
                "screen_model":
                    sum(1 for r in excluded_rows if r["stage"] == "screen"),
                "borderline_resolution":
                    sum(1 for r in excluded_rows
                        if r["stage"] == "borderline_resolution"),
            },
        },
        "records_included": len(included_rows),
        "borderline_pending": len(pending_rows),
        "conservation_checks": checks,
        "conserved": all(c["ok"] for c in checks),
        "counting_rule": ("每个计数均为对 decision_ledger.jsonl 行的实际计数"
                          "（identified/duplicates 来自 dedup_summary.json 的"
                          "实际去重组数），无任何断言式数字。"),
    }
    return flow, ledger, dedup


def render_flow_md(flow, dedup):
    lines = []
    lines.append("# PRISMA 风格筛选流量（由 decision_ledger.jsonl 逐行重算）")
    lines.append("")
    lines.append("> 本表为 PRISMA 2020 流量图针对**离线多源候选集**的适配"
                 "（详见 references/prisma-counting.md）；所有计数由脚本"
                 "对账本行实际计数得到，非人工断言。")
    lines.append("")
    lines.append("```")
    lines.append("识别 identified")
    for src, n in sorted(flow["records_identified"]["per_source"].items()):
        lines.append("  %-12s %d" % (src, n))
    lines.append("  %-12s %d" % ("total", flow["records_identified"]["total"]))
    lines.append("    │")
    lines.append("    ├─ 去重移除 duplicates_removed: %d"
                 % flow["duplicates_removed"])
    for g in dedup.get("duplicate_groups", []):
        lines.append("    │    · %s ← %s (%s)"
                     % (g.get("kept_record_id") or g.get("kept"),
                        g.get("absorbed"), g.get("match")))
    lines.append("    ▼")
    lines.append("初筛 screened: %d" % flow["records_screened"])
    if flow["records_unjudged"]:
        lines.append("    ├─ 未判定 unjudged: %d" % flow["records_unjudged"])
    lines.append("    ├─ 排除 excluded: %d"
                 % flow["records_excluded"]["total"])
    for cid, n in sorted(flow["records_excluded"]["per_criterion"].items()):
        lines.append("    │    · %s: %d" % (cid, n))
    lines.append("    ├─ 边界待决 borderline_pending: %d"
                 % flow["borderline_pending"])
    lines.append("    ▼")
    lines.append("纳入 included: %d" % flow["records_included"])
    lines.append("```")
    lines.append("")
    lines.append("## 守恒校验")
    lines.append("")
    lines.append("| 不变量 | 左侧 | 右侧 | 成立 |")
    lines.append("|---|---|---|---|")
    for c in flow["conservation_checks"]:
        lines.append("| %s | %d | %d | %s |"
                     % (c["invariant"], c["lhs"], c["rhs"],
                        "✅" if c["ok"] else "❌"))
    lines.append("")
    return "\n".join(lines)


def cmd_flow(args):
    work_dir = args.work
    flow, ledger, dedup = compute_flow(work_dir)
    write_json(os.path.join(work_dir, "prisma_flow.json"), flow)
    write_text(os.path.join(work_dir, "prisma_flow.md"),
               render_flow_md(flow, dedup))
    if not flow["conserved"]:
        print("flow: 守恒校验失败！", file=sys.stderr)
        return 3
    print("flow: identified=%d dedup=%d screened=%d excluded=%d included=%d "
          "borderline_pending=%d (conserved)"
          % (flow["records_identified"]["total"], flow["duplicates_removed"],
             flow["records_screened"], flow["records_excluded"]["total"],
             flow["records_included"], flow["borderline_pending"]))
    return 0


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------

def cmd_report(args):
    work_dir = args.work
    criteria = load_criteria(args.criteria)
    records = read_jsonl(os.path.join(work_dir, "normalized.jsonl"))
    records_by_id = {r["record_id"]: r for r in records}
    ledger = read_jsonl(os.path.join(work_dir, "decision_ledger.jsonl"))
    flow, _, dedup = compute_flow(work_dir)
    queue_path = os.path.join(work_dir, "borderline_queue.json")
    queue = read_json(queue_path, "borderline_queue.json") if os.path.exists(
        queue_path) else {"pending": [], "unjudged": [], "resolved": []}
    crit_by_id = {c["id"]: c for c in criteria["criteria"]}

    L = []
    L.append("# 筛选判定报告（screening_report.md）")
    L.append("")
    L.append("> 本报告由脚本生成；所有计数来自 decision_ledger.jsonl 重算。")
    L.append("")

    L.append("## 1. 资格标准（编译自 task.md，含原文引用）")
    L.append("")
    L.append("| 标准 ID | 类型 | 定义 | task.md 原文依据 | 机器可判 | 状态 |")
    L.append("|---|---|---|---|---|---|")
    for c in criteria["criteria"]:
        machine = "是（%s）" % c["machine"]["type"] if isinstance(
            c.get("machine"), dict) else "否（需判定）"
        status = "已确认" if not c.get("derived") else "derived_needs_confirmation"
        L.append("| %s | %s | %s | “%s” | %s | %s |"
                 % (c["id"], c["kind"], c["definition"],
                    c["source_quote"], machine, status))
    L.append("")
    if criteria.get("derived_needs_confirmation"):
        L.append("⚠️ 本批次标准整体标记 `derived_needs_confirmation`：标准由模型从 "
                 "task.md 编译而来，**需人工二次确认登记**后方可视为定论。")
        L.append("")

    L.append("## 2. 纳入清单（含判定理由）")
    L.append("")
    included = [r for r in ledger if r["decision"] == "include"]
    included.sort(key=lambda r: (r.get("rank") is None, r.get("rank") or 0,
                                 r["record_id"]))
    if not included:
        L.append("（无纳入记录）")
    for r in included:
        rec = records_by_id[r["record_id"]]
        rank = "rank=%d " % r["rank"] if r.get("rank") else ""
        L.append("- **%s** %s— %s（%s）" % (
            r["record_id"], rank, rec.get("title") or "(无标题)",
            rec.get("year") or "年份缺失"))
        L.append("  - 依据标准：%s" % ", ".join(r["criterion_ids"]))
        if r.get("evidence"):
            L.append("  - 证据（逐字引用）：“%s”" % r["evidence"])
        if r.get("rationale"):
            L.append("  - 理由：%s" % r["rationale"])
        if r.get("basis") == "title-only":
            L.append("  - ⚠️ 判定降级：记录缺摘要，仅凭标题判定（title-only）")
    L.append("")

    L.append("## 3. 排除原因矩阵")
    L.append("")
    excluded = [r for r in ledger if r["decision"] == "exclude"]
    L.append("| 记录 | 标题（截断） | 排除标准 | 证据 | 判定者 |")
    L.append("|---|---|---|---|---|")
    for r in excluded:
        rec = records_by_id[r["record_id"]]
        title = (rec.get("title") or "(无标题)")
        if len(title) > 60:
            title = title[:57] + "..."
        ev = r.get("evidence") or ""
        if len(ev) > 80:
            ev = ev[:77] + "..."
        L.append("| %s | %s | %s | %s | %s |"
                 % (r["record_id"], title, ", ".join(r["criterion_ids"]),
                    ev, r["decided_by"]))
    L.append("")

    L.append("## 4. 边界队列与裁定")
    L.append("")
    resolved = [r for r in ledger if r["stage"] == "borderline_resolution"]
    if resolved:
        for r in resolved:
            L.append("- **%s** → %s（依据 %s）：%s"
                     % (r["record_id"], r["decision"],
                        ", ".join(r["criterion_ids"]),
                        r.get("rationale") or "（无理由说明）"))
    else:
        L.append("（无已裁定边界记录）")
    if queue.get("pending"):
        L.append("")
        L.append("⚠️ 待决边界记录：%s" % ", ".join(queue["pending"]))
    if queue.get("unjudged"):
        L.append("⚠️ 未判定记录：%s" % ", ".join(queue["unjudged"]))
    L.append("")

    L.append("## 5. 流量计数（重算值）")
    L.append("")
    L.append("| 阶段 | 计数 |")
    L.append("|---|---|")
    L.append("| 识别（各源合计） | %d |" % flow["records_identified"]["total"])
    for src, n in sorted(flow["records_identified"]["per_source"].items()):
        L.append("| — %s | %d |" % (src, n))
    L.append("| 去重移除 | %d |" % flow["duplicates_removed"])
    L.append("| 初筛 | %d |" % flow["records_screened"])
    L.append("| 排除 | %d |" % flow["records_excluded"]["total"])
    for cid, n in sorted(flow["records_excluded"]["per_criterion"].items()):
        cdef = crit_by_id.get(cid, {}).get("definition", "")
        L.append("| — %s（%s） | %d |" % (cid, cdef, n))
    L.append("| 边界待决 | %d |" % flow["borderline_pending"])
    L.append("| 纳入 | %d |" % flow["records_included"])
    L.append("")

    L.append("## 6. 局限与诚实声明")
    L.append("")
    title_only = [r for r in records if not r.get("has_abstract")]
    if title_only:
        L.append("- 以下记录缺摘要，判定降级为 title-only：%s"
                 % ", ".join(r["record_id"] for r in title_only))
    insuff = [r for r in ledger if r.get("evidence_kind")
              == "insufficient_evidence"]
    if insuff:
        L.append("- 以下记录证据不足（insufficient_evidence）：%s"
                 % ", ".join(r["record_id"] for r in insuff))
    if dedup.get("quarantined_materials"):
        for q in dedup["quarantined_materials"]:
            L.append("- 材料被隔离：%s（%s）" % (q["material"], q["reason"]))
    if criteria.get("derived_needs_confirmation"):
        L.append("- 资格标准由 task.md 编译而来且标记 derived_needs_confirmation，"
                 "未经人工二次确认前结论不构成最终筛选。")
    L.append("- 本技能只做题录级（标题/摘要/元数据）资格判定，**不做全文质量评价**；"
             "判定证据仅限记录内文本的逐字引用。")
    L.append("- 去重为最小确定性规则（DOI 精确 / 标题+年份+第一作者全同），"
             "仅用于喂流量计数，不做模糊合并。")
    L.append("")
    write_text(os.path.join(work_dir, "screening_report.md"), "\n".join(L))
    print("report: screening_report.md written (%d lines)" % len(L))
    return 0


# ---------------------------------------------------------------------------
# finalize
# ---------------------------------------------------------------------------

def fill_contract(contract_spec, work_dir, candidate_set, flow, criteria,
                  queue):
    filled = {}
    unresolved = []
    for key in sorted((contract_spec or {}).keys()):
        target = None
        low = key.lower()
        for needles, name in CONTRACT_FILLERS:
            if any(n in low for n in needles):
                target = name
                break
        if target == "candidate_set":
            filled[key] = candidate_set
        elif target == "prisma_flow":
            filled[key] = flow
        elif target == "exclusion_reasons":
            filled[key] = flow["records_excluded"]["per_criterion"]
        elif target == "criteria":
            filled[key] = criteria["criteria"]
        elif target == "borderline_resolutions":
            filled[key] = {
                "resolved": queue.get("resolved", []),
                "pending": queue.get("pending", []),
            }
        elif target == "screening_report_path":
            filled[key] = "screening_report.md"
        else:
            filled[key] = None
            unresolved.append(key)
    return filled, unresolved


def cmd_finalize(args):
    work_dir = args.work
    out_dir = args.output
    ensure_dir(out_dir)
    case_echo = read_json(os.path.join(work_dir, "case_echo.json"),
                          "case_echo.json")
    criteria = load_criteria(args.criteria) if args.criteria else None
    records = read_jsonl(os.path.join(work_dir, "normalized.jsonl"))
    records_by_id = {r["record_id"]: r for r in records}
    ledger = read_jsonl(os.path.join(work_dir, "decision_ledger.jsonl"))
    queue = read_json(os.path.join(work_dir, "borderline_queue.json"),
                      "borderline_queue.json")
    flow, _, dedup = compute_flow(work_dir)

    ledger_by_id = {r["record_id"]: r for r in ledger}
    included = [r for r in ledger if r["decision"] == "include"]
    included.sort(key=lambda r: (r.get("rank") is None, r.get("rank") or 0,
                                 r["record_id"]))
    candidate_set = []
    for pos, r in enumerate(included, 1):
        rec = records_by_id[r["record_id"]]
        candidate_set.append({
            "rank": r.get("rank") or pos,
            "record_id": r["record_id"],
            "title": rec.get("title"),
            "year": rec.get("year"),
            "doi": rec.get("doi"),
            "pmid": rec.get("pmid"),
            "sources": rec.get("sources"),
            "criterion_ids": r["criterion_ids"],
            "rationale": r.get("rationale"),
            "evidence_quote": r.get("evidence"),
        })
    write_json(os.path.join(work_dir, "candidate_set.json"), candidate_set)

    contract_filled, unresolved = fill_contract(
        case_echo.get("output_contract"), work_dir, candidate_set, flow,
        criteria or {"criteria": []}, queue)

    uncertainty = []
    if queue.get("pending"):
        uncertainty.append("borderline 待决: %s" % ", ".join(queue["pending"]))
    if queue.get("unjudged"):
        uncertainty.append("未判定记录: %s" % ", ".join(queue["unjudged"]))
    if criteria and criteria.get("derived_needs_confirmation"):
        uncertainty.append("资格标准标记 derived_needs_confirmation，"
                           "需人工二次确认登记")
    for rec in records:
        if not rec.get("has_abstract"):
            uncertainty.append("记录 %s 缺摘要，判定降级 title-only"
                               % rec["record_id"])
    for q in dedup.get("quarantined_materials", []):
        uncertainty.append("材料被隔离: %s (%s)" % (q["material"], q["reason"]))
    if unresolved:
        uncertainty.append("以下 output_contract 字段无法填充（已置 null）: %s"
                           % ", ".join(unresolved))

    status = "ok"
    exit_code = 0
    if (queue.get("pending") or queue.get("unjudged") or unresolved
            or (criteria and criteria.get("derived_needs_confirmation"))
            or dedup.get("quarantined_materials")):
        status = "partial"
        exit_code = 2
    if not flow.get("conserved"):
        status = "error"
        exit_code = 3

    sources = []
    for entry in dedup.get("sources_manifest", []):
        sources.append({"material": entry["material"], "kind": entry["kind"],
                        "records": entry.get("records", 0),
                        "sha256": entry["sha256"]})

    checks = [
        {"check": "prisma_conservation", "ok": flow.get("conserved", False)},
        {"check": "every_exclude_has_criterion",
         "ok": all(r["criterion_ids"] for r in ledger
                   if r["decision"] == "exclude")},
        {"check": "all_contract_fields_addressed",
         "ok": not unresolved},
        {"check": "no_borderline_pending", "ok": not queue.get("pending")},
    ]

    result = {
        "case_id": case_echo["case_id"],
        "skill_name": SKILL_NAME,
        "skill_version": VERSION,
        "status": status,
        "research_question": case_echo.get("research_question"),
        "contract": contract_filled,
        "unresolved_contract_fields": unresolved,
        "products": {
            "decision_ledger": "decision_ledger.jsonl",
            "prisma_flow_json": "prisma_flow.json",
            "prisma_flow_md": "prisma_flow.md",
            "screening_report": "screening_report.md",
            "candidate_set": "candidate_set.json",
            "borderline_queue": "borderline_queue.json",
            "normalized": "normalized.jsonl",
            "dedup_summary": "dedup_summary.json",
        },
        "sources": sources,
        "uncertainty": uncertainty,
        "change_records": [
            "parse: 嗅探并规范化材料，最小去重喂流量计数",
            "criteria: 资格标准来自 task.md，由模型编译"
            + ("（derived_needs_confirmation，待人工确认）"
               if criteria and criteria.get("derived_needs_confirmation")
               else "并经人工确认登记"),
            "prescreen: 机器可判标准由脚本预判并落账",
            "judgments: 模型批量判定，引用经逐珠子串校验",
            "ledger/flow/report: 计数全部由账本行重算",
        ],
        "counts": {
            "identified": flow["records_identified"]["total"],
            "duplicates_removed": flow["duplicates_removed"],
            "screened": flow["records_screened"],
            "excluded": flow["records_excluded"]["total"],
            "included": flow["records_included"],
            "borderline_pending": flow["borderline_pending"],
        },
        "checks": checks,
    }
    write_json(os.path.join(out_dir, "result.json"), result)
    print("finalize: status=%s (exit %d), unresolved=%s"
          % (status, exit_code, unresolved))
    return exit_code


# ---------------------------------------------------------------------------
# selfcheck
# ---------------------------------------------------------------------------

def cmd_selfcheck(args):
    work_dir = args.work
    out_dir = args.output
    failures = []

    result_path = os.path.join(out_dir, "result.json")
    if not os.path.exists(result_path):
        print("SELFCHECK FAIL: result.json 缺失", file=sys.stderr)
        return 1
    result = read_json(result_path, "result.json")
    case_echo = read_json(os.path.join(work_dir, "case_echo.json"),
                          "case_echo.json")
    contract_spec = case_echo.get("output_contract") or {}

    # 1. 契约键
    contract = result.get("contract") or {}
    unresolved = set(result.get("unresolved_contract_fields") or [])
    for key in contract_spec:
        if key not in contract:
            failures.append("契约字段 %r 未出现在 result.json.contract" % key)
        elif contract[key] is None and key not in unresolved:
            failures.append("契约字段 %r 为 null 但未列入 unresolved_contract_fields"
                            % key)

    # 2. 守恒
    flow, ledger, dedup = compute_flow(work_dir)
    if not flow["conserved"]:
        for c in flow["conservation_checks"]:
            if not c["ok"]:
                failures.append("守恒失败: %s (%d != %d)"
                                % (c["invariant"], c["lhs"], c["rhs"]))

    # 3. 每条 exclude ≥1 标准；criterion id 存在
    criteria_path = args.criteria
    crit_ids = set()
    if criteria_path and os.path.exists(criteria_path):
        crit_ids = {c["id"] for c in load_criteria(criteria_path)["criteria"]}
    for r in ledger:
        if r["decision"] == "exclude" and not r["criterion_ids"]:
            failures.append("exclude 行 %s 无 criterion id" % r["record_id"])
        if crit_ids:
            for cid in r["criterion_ids"]:
                if cid not in crit_ids:
                    failures.append("账本行 %s 引用未知标准 %s"
                                    % (r["record_id"], cid))

    # 4. 引用逐珠核验
    records = read_jsonl(os.path.join(work_dir, "normalized.jsonl"))
    records_by_id = {r["record_id"]: r for r in records}
    for r in ledger:
        if r.get("evidence_kind") == "quote":
            blob = record_text_blob(records_by_id[r["record_id"]])
            if not r.get("evidence") or r["evidence"] not in blob:
                failures.append("账本行 %s 的 evidence 未通过逐珠子串核验"
                                % r["record_id"])

    # 5. 计数重算一致性（result.json.counts vs 账本）
    counts = result.get("counts") or {}
    recomputed = {
        "identified": flow["records_identified"]["total"],
        "duplicates_removed": flow["duplicates_removed"],
        "screened": flow["records_screened"],
        "excluded": flow["records_excluded"]["total"],
        "included": flow["records_included"],
        "borderline_pending": flow["borderline_pending"],
    }
    for k, v in recomputed.items():
        if counts.get(k) != v:
            failures.append("counts.%s=%r 与重算值 %r 不一致"
                            % (k, counts.get(k), v))

    if failures:
        for f in failures:
            print("SELFCHECK FAIL: %s" % f, file=sys.stderr)
        print("selfcheck: %d 项失败" % len(failures), file=sys.stderr)
        return 1
    print("selfcheck: 全部通过（契约键/守恒/排除理由/引用核验/计数重算）")
    return 0


# ---------------------------------------------------------------------------
# 骨架与 run-all
# ---------------------------------------------------------------------------

def scaffold_result(out_dir, case_id, note):
    ensure_dir(out_dir)
    scaffold = {
        "case_id": case_id,
        "skill_name": SKILL_NAME,
        "skill_version": VERSION,
        "status": "partial",
        "contract": {},
        "unresolved_contract_fields": [],
        "products": {},
        "sources": [],
        "uncertainty": [note],
        "change_records": ["scaffold written before full run: %s" % note],
        "counts": {},
        "checks": [],
    }
    write_json(os.path.join(out_dir, "result.json"), scaffold)


def cmd_run_all(args):
    input_dir, work_dir, out_dir = args.input, args.work, args.output
    ensure_dir(work_dir)
    # STEP 0：先写骨架（诚实 partial），再读任何输入
    case_id = None
    case_path = os.path.join(input_dir, "case.json")
    if os.path.exists(case_path):
        try:
            case_id = (read_json(case_path, "case.json") or {}).get("case_id")
        except InvalidInput:
            case_id = None
    scaffold_result(out_dir, case_id, "run-all 启动骨架")

    rc = cmd_parse(argparse.Namespace(input=input_dir, work=work_dir))
    if rc != 0:
        return rc

    if not args.criteria or not os.path.exists(args.criteria):
        scaffold_result(out_dir, case_id,
                        "criteria.json 缺失：资格标准编译（模型步骤）尚未完成，"
                        "无法进行判定；骨架已保留，请先提供 --criteria")
        print("run-all: 缺少 --criteria 文件，已保留 result.json 骨架，"
              "退出 2（诚实降级）", file=sys.stderr)
        return 2

    ns = argparse.Namespace
    rc = cmd_prescreen(ns(work=work_dir, criteria=args.criteria))
    if rc:
        return rc
    if args.judgments and os.path.exists(args.judgments):
        rc = cmd_validate_judgments(ns(work=work_dir, criteria=args.criteria,
                                       judgments=args.judgments))
        if rc:
            return rc
    else:
        print("run-all: 未提供 judgments.json，继续（将产生 unjudged/partial）",
              file=sys.stderr)
    rc = cmd_ledger(ns(work=work_dir, criteria=args.criteria,
                       judgments=args.judgments if args.judgments
                                                  and os.path.exists(
                                                      args.judgments) else None,
                       borderline_decisions=args.borderline_decisions))
    if rc:
        return rc
    rc = cmd_flow(ns(work=work_dir))
    if rc:
        return rc
    rc = cmd_report(ns(work=work_dir, criteria=args.criteria))
    if rc:
        return rc
    rc = cmd_finalize(ns(work=work_dir, output=out_dir,
                         criteria=args.criteria))
    finalize_rc = rc
    sc = cmd_selfcheck(ns(work=work_dir, output=out_dir,
                          criteria=args.criteria))
    if sc != 0:
        return 3
    return finalize_rc


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser():
    p = argparse.ArgumentParser(
        prog="screening_ledger.py",
        description="筛选判定账本：离线多源文献筛选的 include/exclude 判定、"
                    "边界队列与 PRISMA 风格流量重算。退出码 0 ok / 2 partial / "
                    "3 invalid input（selfcheck 为 0/1）。")
    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("parse", help="嗅探+规范化+最小去重")
    sp.add_argument("--input", required=True, help="含 case.json 的输入目录")
    sp.add_argument("--work", required=True, help="工作目录")
    sp.set_defaults(func=cmd_parse)

    sp = sub.add_parser("prescreen", help="机器可判标准预判")
    sp.add_argument("--work", required=True)
    sp.add_argument("--criteria", required=True)
    sp.set_defaults(func=cmd_prescreen)

    sp = sub.add_parser("validate-judgments", help="严格校验判定文件")
    sp.add_argument("--work", required=True)
    sp.add_argument("--criteria", required=True)
    sp.add_argument("--judgments", required=True)
    sp.set_defaults(func=cmd_validate_judgments)

    sp = sub.add_parser("ledger", help="合并判定 → decision_ledger.jsonl")
    sp.add_argument("--work", required=True)
    sp.add_argument("--criteria", required=True)
    sp.add_argument("--judgments", default=None)
    sp.add_argument("--borderline-decisions", default=None)
    sp.set_defaults(func=cmd_ledger)

    sp = sub.add_parser("flow", help="由账本重算 PRISMA 风格流量")
    sp.add_argument("--work", required=True)
    sp.set_defaults(func=cmd_flow)

    sp = sub.add_parser("report", help="生成 screening_report.md")
    sp.add_argument("--work", required=True)
    sp.add_argument("--criteria", required=True)
    sp.set_defaults(func=cmd_report)

    sp = sub.add_parser("finalize", help="candidate_set.json + result.json")
    sp.add_argument("--work", required=True)
    sp.add_argument("--output", required=True)
    sp.add_argument("--criteria", default=None)
    sp.set_defaults(func=cmd_finalize)

    sp = sub.add_parser("selfcheck", help="契约/守恒/引用/计数自查 (exit 0/1)")
    sp.add_argument("--work", required=True)
    sp.add_argument("--output", required=True)
    sp.add_argument("--criteria", default=None)
    sp.set_defaults(func=cmd_selfcheck)

    sp = sub.add_parser("run-all", help="全链路（诚实降级）")
    sp.add_argument("--input", required=True)
    sp.add_argument("--work", required=True)
    sp.add_argument("--output", required=True)
    sp.add_argument("--criteria", default=None)
    sp.add_argument("--judgments", default=None)
    sp.add_argument("--borderline-decisions", default=None)
    sp.set_defaults(func=cmd_run_all)
    return p


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except InvalidInput as exc:
        print("ERROR(invalid input): %s" % exc, file=sys.stderr)
        return 3
    except DegradedRun as exc:
        print("PARTIAL: %s" % exc, file=sys.stderr)
        return 2
    except Exception as exc:  # 顶层兜底：不裸栈
        print("ERROR(unexpected): %s: %s" % (type(exc).__name__, exc),
              file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
