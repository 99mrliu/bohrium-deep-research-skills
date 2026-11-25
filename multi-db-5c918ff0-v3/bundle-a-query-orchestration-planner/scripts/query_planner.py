#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
query_planner.py — 多数据库联合检索的"上游查询编排与来源调度"引擎。

职责边界(严格):只负责"记录被合并之前"的一切——
  parse     读取 case.json + task.md,结构嗅探每份离线材料,写 case_summary.json;
  plan      依据模型产出的 facets.json,为每个来源库编译适配其语法/分页/配额的
            查询计划 query_plan.json;
  reconcile 将计划与实际在场的材料响应对账,写 coverage_declaration.json 与
            query_ledger.jsonl;响应缺失的数据库显式声明覆盖缺口,绝不静默跳过;
  finalize  汇总 result.json(含 output_contract 全部字段,无法填充者置 null 并登记);
  selfcheck 交付前自查(契约完备/哈希一致/计数可重算/无静默丢弃),退出码 0/1;
  run-all   parse→plan→reconcile→finalize→selfcheck 的顺序编排,诚实降级。

本脚本不做去重、不做合并、不做覆盖统计之外的下游处理,不访问网络。
Python 3 标准库;确定性(无墙钟、无随机、排序落盘);幂等(同输入同输出)。

退出码约定:0=正常(允许 status=partial 的诚实降级结果);1=自查未通过;
2=材料/输入不足导致的诚实降级(如 facets.json 缺失);3=输入非法(case.json 缺失/不可解析)。

数据库能力事实:以下 DB_CAPABILITIES 常量转录自 references/db-capabilities.md
(转录日期 2026-11;若该文件可定位,plan 会同时记录其 sha256 以便溯源)。
"""

import argparse
import csv
import hashlib
import io
import json
import os
import re
import sys

SKILL_NAME = "query-orchestration-planner"
SKILL_VERSION = "1.0.0"

EXIT_OK = 0
EXIT_SELFCHECK_FAIL = 1
EXIT_DEGRADED = 2
EXIT_BAD_INPUT = 3

# ---------------------------------------------------------------------------
# 数据库能力常量(转录自 references/db-capabilities.md;仅供离线规划,绝不发起调用)
# ---------------------------------------------------------------------------
DB_CAPABILITIES = {
    "crossref": {
        "display": "Crossref REST API",
        "query_fields": ["query.bibliographic", "query.author", "query.title", "query"],
        "filters": ["from-pub-date", "until-pub-date", "type", "has-full-text", "from-index-date"],
        "max_rows": 1000,
        "default_rows": 100,
        "pagination": "offset+rows;深分页建议 cursor(* 起翻)",
        "sort": ["relevance", "published", "updated", "deposited"],
        "select_supported": True,
        "echo_field": "message.query",
        "truncation_check": "message.total-results > len(message.items)",
        "quota": {"max_requests_per_run": 20, "timeout_seconds": 30,
                   "retry": "指数退避至多 3 次;尊重 Retry-After;礼貌池需 mailto"},
        "strength": "跨学科书目元数据覆盖面最广,适合作为候选池骨架",
        "weakness": "无摘要/全文字段,outcome 类证据需下游核对原文",
    },
    "europepmc": {
        "display": "Europe PMC REST API",
        "query_fields": ["TITLE", "TITLE_ABS", "AUTH", "PUB_YEAR", "JOURNAL", "DOI", "ABSTRACT"],
        "operators": ["AND", "OR", "NOT"],
        "max_page_size": 1000,
        "default_page_size": 100,
        "pagination": "cursorMark(* 起翻,响应回传 nextCursorMark)",
        "sort": ["relevance(默认)", "CITED desc", "P_PDATE_D desc", "FIRST_PDATE_D desc"],
        "select_supported": False,
        "echo_field": "request.queryString(部分端点不回响)",
        "truncation_check": "hitCount > len(resultList.result)",
        "quota": {"max_requests_per_run": 20, "timeout_seconds": 30,
                   "retry": "指数退避至多 3 次"},
        "strength": "生物医学摘要与受控词字段检索强,适合 intervention/outcome 概念块",
        "weakness": "学科偏向生物医学,农学/植物学等 population 覆盖偏弱",
    },
    "publisher": {
        "display": "出版方站点/导出(generic profile)",
        "query_fields": ["站点关键词框(语法不保证公开)"],
        "max_page_size": None,
        "default_page_size": None,
        "pagination": "依导出文件或站点翻页而定,规划时仅登记意图",
        "sort": ["站点默认(通常 relevance 或 date)"],
        "select_supported": False,
        "echo_field": "通常不回响查询",
        "truncation_check": "导出文件无法可靠判定,需人工核对站点计数",
        "quota": {"max_requests_per_run": 5, "timeout_seconds": 60,
                   "retry": "保守:至多 1 次重试"},
        "strength": "出版社自有全文与优先出版(ahead-of-print)",
        "weakness": "语法/导出格式站点各异,计划只能给出中性关键词与注意事项",
    },
}

# 学科提示词:Europe PMC 对这些 population 词覆盖偏弱(诚实声明用)
BIOMED_WEAK_HINTS = {"oryza", "rice", "wheat", "maize", "plant", "crop",
                     "agronomy", "soil", "cultivar"}

CONTRACT_FILL_RULES = [
    # (关键词, 填充函数名)——按序匹配契约字段名(小写包含)
    ("candidate", "fill_candidate_set"),
    ("coverage", "fill_coverage_summary"),
    ("ledger", "fill_ledger_pointer"),
    ("plan", "fill_plan_pointer"),
    ("question", "fill_open_questions"),
    ("status", "fill_status_report"),
    ("method", "fill_method_notes"),
    ("note", "fill_method_notes"),
]
# 明确属于下游职责、本技能绝不填充的字段名关键词
DOWNSTREAM_ONLY_HINTS = ("evidence", "merged", "dedup", "answer", "synthesis")


# ---------------------------------------------------------------------------
# 基础工具
# ---------------------------------------------------------------------------
def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json(path, obj):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")


def write_jsonl(path, rows):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def read_json_file(path):
    """返回 (obj, error, encoding_note)。容错 utf-8-sig / latin-1。"""
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError as e:
        return None, "read_error:%s" % e, None
    note = None
    for enc in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            text = raw.decode(enc)
            if enc != "utf-8":
                note = "encoding_fallback:%s" % enc
            break
        except UnicodeDecodeError:
            continue
    else:
        return None, "decode_error:not utf-8/utf-8-sig/latin-1", None
    try:
        return json.loads(text), None, note
    except json.JSONDecodeError as e:
        return None, "json_error:%s" % e, note


def tokenize(text):
    return re.findall(r"[a-z0-9]+", (text or "").lower())


def load_case(input_dir):
    """读取 case.json;返回 (case_dict, error)。"""
    case_path = os.path.join(input_dir, "case.json")
    if not os.path.isfile(case_path):
        return None, "case.json 缺失: %s" % case_path
    case, err, _ = read_json_file(case_path)
    if err:
        return None, "case.json 不可解析: %s" % err
    if not isinstance(case, dict) or not case.get("case_id"):
        return None, "case.json 缺少 case_id 字段"
    return case, None


def extract_contract_fields(case):
    """从 case.output_contract 提取字段名列表,兼容多种形状。"""
    oc = case.get("output_contract")
    names = []
    if isinstance(oc, dict):
        fields = oc.get("fields")
        if isinstance(fields, list):
            for f in fields:
                if isinstance(f, dict) and f.get("name"):
                    names.append(str(f["name"]))
                elif isinstance(f, str):
                    names.append(f)
        else:
            for k in oc:
                if k != "fields":
                    names.append(str(k))
    elif isinstance(oc, list):
        for f in oc:
            if isinstance(f, dict) and f.get("name"):
                names.append(str(f["name"]))
            elif isinstance(f, str):
                names.append(f)
    # 保序去重
    seen, out = set(), []
    for n in names:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out


def extract_source_dbs(case, summary_files):
    """来源库集合:优先 case.source_dbs;否则按在场材料类型推断;兜底三库。"""
    dbs = case.get("source_dbs")
    if isinstance(dbs, list) and dbs:
        return [str(d) for d in dbs]
    inferred = []
    type2db = {"crossref": "crossref", "europepmc": "europepmc",
               "publisher_json": "publisher", "publisher_jsonl": "publisher",
               "publisher_csv": "publisher"}
    for f in summary_files:
        db = type2db.get(f.get("sniffed_type"))
        if db and db not in inferred:
            inferred.append(db)
    return inferred or ["crossref", "europepmc", "publisher"]


# ---------------------------------------------------------------------------
# 材料嗅探
# ---------------------------------------------------------------------------
def sniff_json_obj(obj, relpath):
    """对解析成功的 JSON 值判定类型。"""
    name = os.path.basename(relpath).lower()
    if isinstance(obj, dict):
        msg = obj.get("message")
        if isinstance(msg, dict) and isinstance(msg.get("items"), list):
            return "crossref", msg.get("items")
        rl = obj.get("resultList")
        if isinstance(rl, dict) and isinstance(rl.get("result"), list):
            return "europepmc", rl.get("result")
        if isinstance(obj.get("nodes"), list) and isinstance(obj.get("edges"), list):
            return "reference_graph", obj.get("nodes")
        if "reference_graph" in name and isinstance(obj.get("references", obj.get("nodes")), list):
            return "reference_graph", obj.get("references", obj.get("nodes"))
        state_keys = {"last_import", "seen_dois", "imported_ids", "cursor", "state_version"}
        if state_keys & set(obj.keys()) or "import_state" in name:
            seen = obj.get("seen_dois") or obj.get("imported_ids") or []
            return "import_state", seen if isinstance(seen, list) else []
        for key in ("records", "articles", "results", "items", "publications"):
            v = obj.get(key)
            if isinstance(v, list) and (not v or isinstance(v[0], dict)):
                return "publisher_json", v
        return "unknown", None
    if isinstance(obj, list):
        if obj and isinstance(obj[0], dict):
            keys = set()
            for it in obj[:5]:
                keys |= set(it.keys())
            if keys & {"doi", "DOI", "title", "pmid", "journal"}:
                return "publisher_json", obj
        return "unknown", None
    return "unknown", None


def sniff_file(path, relpath):
    """结构嗅探单个材料文件;unknown/unparseable 一律隔离登记而非丢弃。"""
    entry = {"path": relpath, "present": True, "sha256": None, "bytes": 0,
             "sniffed_type": "unknown", "record_count": 0,
             "truncation_detected": False, "truncation_detail": None,
             "encoding_note": None, "quarantined": False, "notes": []}
    try:
        entry["bytes"] = os.path.getsize(path)
        entry["sha256"] = sha256_file(path)
    except OSError as e:
        entry["present"] = False
        entry["notes"].append("io_error:%s" % e)
        return entry

    ext = os.path.splitext(relpath)[1].lower()
    raw_head = b""
    try:
        with open(path, "rb") as f:
            raw_head = f.read(8192)
    except OSError:
        pass
    head_text = None
    for enc in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            head_text = raw_head.decode(enc)
            if enc != "utf-8":
                entry["encoding_note"] = "encoding_fallback:%s" % enc
            break
        except UnicodeDecodeError:
            continue

    if ext in (".jsonl",) or (ext in (".txt", ".ndjson") and head_text and
                              head_text.lstrip().startswith("{")):
        rows, bad = [], 0
        try:
            with io.open(path, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rows.append(json.loads(line))
                    except json.JSONDecodeError:
                        bad += 1
        except OSError as e:
            entry["notes"].append("io_error:%s" % e)
        if rows:
            entry["sniffed_type"] = "publisher_jsonl"
            entry["record_count"] = len(rows)
            if bad:
                entry["notes"].append("jsonl_bad_lines:%d" % bad)
                entry["truncation_detected"] = True
                entry["truncation_detail"] = "%d 行不可解析,疑截断或脏行" % bad
            return entry
        entry["notes"].append("jsonl_empty_or_unparseable")

    if ext == ".csv" or (head_text and "," in (head_text.splitlines() or [""])[0]
                         and not head_text.lstrip().startswith(("{", "["))):
        try:
            with io.open(path, "r", encoding="utf-8", errors="replace", newline="") as f:
                sample = f.read(4096)
                f.seek(0)
                try:
                    dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
                except csv.Error:
                    dialect = csv.excel
                rows = list(csv.reader(f, dialect))
            if len(rows) >= 2:
                entry["sniffed_type"] = "publisher_csv"
                entry["record_count"] = len(rows) - 1
                entry["notes"].append("csv_header:%s" % ",".join(rows[0])[:200])
                return entry
            entry["notes"].append("csv_too_few_rows")
        except (OSError, csv.Error) as e:
            entry["notes"].append("csv_error:%s" % e)

    if ext in (".json", ".txt", "") or (head_text and head_text.lstrip().startswith(("{", "["))):
        obj, err, note = read_json_file(path)
        if note:
            entry["encoding_note"] = note
        if err:
            entry["sniffed_type"] = "unparseable"
            entry["quarantined"] = True
            entry["notes"].append(err)
            return entry
        stype, records = sniff_json_obj(obj, relpath)
        entry["sniffed_type"] = stype
        if records is not None:
            entry["record_count"] = len(records)
        if stype == "crossref":
            total = obj.get("message", {}).get("total-results")
            got = entry["record_count"]
            if isinstance(total, int) and total > got:
                entry["truncation_detected"] = True
                entry["truncation_detail"] = (
                    "total-results=%d 而 items=%d:响应为单页截断" % (total, got))
        elif stype == "europepmc":
            hit = obj.get("hitCount")
            got = entry["record_count"]
            try:
                hit_i = int(hit)
                if hit_i > got:
                    entry["truncation_detected"] = True
                    entry["truncation_detail"] = (
                        "hitCount=%d 而 result=%d:响应为单页截断" % (hit_i, got))
            except (TypeError, ValueError):
                entry["notes"].append("hitCount 非数值: %r" % (hit,))
        if stype == "unknown":
            entry["quarantined"] = True
            entry["notes"].append("结构不符合任何已知来源模式,已隔离登记")
        return entry

    entry["sniffed_type"] = "unknown"
    entry["quarantined"] = True
    entry["notes"].append("无法识别的格式(扩展名 %s)" % (ext or "无"))
    return entry


# ---------------------------------------------------------------------------
# parse
# ---------------------------------------------------------------------------
def cmd_parse(args):
    input_dir = args.input
    work_dir = args.work
    os.makedirs(work_dir, exist_ok=True)

    case, err = load_case(input_dir)
    if err:
        print("[parse] FATAL: %s" % err, file=sys.stderr)
        summary = {"case_id": None, "fatal": err, "files": [],
                   "missing_declared_materials": [], "undeclared_files": [],
                   "unknown_or_quarantined": []}
        write_json(os.path.join(work_dir, "case_summary.json"), summary)
        return EXIT_BAD_INPUT

    declared = case.get("materials")
    if not isinstance(declared, list):
        declared = []
    declared = [str(m) for m in declared]

    files, missing = [], []
    seen_rel = set()
    for rel in declared:
        seen_rel.add(rel)
        p = os.path.join(input_dir, rel)
        if not os.path.isfile(p):
            missing.append(rel)
            files.append({"path": rel, "present": False, "sha256": None, "bytes": 0,
                          "sniffed_type": "missing", "record_count": 0,
                          "truncation_detected": False, "truncation_detail": None,
                          "encoding_note": None, "quarantined": False,
                          "notes": ["case.json 声明但磁盘缺失"]})
            continue
        files.append(sniff_file(p, rel))

    # 扫描 materials/ 子目录中未声明的文件(不静默丢弃)
    undeclared = []
    mdir = os.path.join(input_dir, "materials")
    if os.path.isdir(mdir):
        for root, _dirs, names in os.walk(mdir):
            for nm in sorted(names):
                rel = os.path.relpath(os.path.join(root, nm), input_dir)
                if rel not in seen_rel:
                    seen_rel.add(rel)
                    entry = sniff_file(os.path.join(root, nm), rel)
                    entry["notes"].append("未在 case.json materials 中声明,按额外材料登记")
                    undeclared.append(rel)
                    files.append(entry)

    files.sort(key=lambda e: e["path"])
    quarantined = [f["path"] for f in files if f.get("quarantined")]
    summary = {
        "case_id": case["case_id"],
        "task_md_present": os.path.isfile(os.path.join(input_dir, "task.md")),
        "files": files,
        "missing_declared_materials": sorted(missing),
        "undeclared_files": sorted(undeclared),
        "unknown_or_quarantined": sorted(quarantined),
        "counts": {
            "declared": len(declared),
            "present": sum(1 for f in files if f.get("present")),
            "missing": len(missing),
            "undeclared_extra": len(undeclared),
            "quarantined": len(quarantined),
            "truncated": sum(1 for f in files if f.get("truncation_detected")),
        },
    }
    write_json(os.path.join(work_dir, "case_summary.json"), summary)
    print("[parse] case_id=%s files=%d missing=%d quarantined=%d truncated=%d"
          % (case["case_id"], len(files), len(missing), len(quarantined),
             summary["counts"]["truncated"]))
    if err is None and summary["counts"]["present"] == 0:
        print("[parse] 无任何在场材料,诚实降级", file=sys.stderr)
        return EXIT_DEGRADED
    return EXIT_OK


# ---------------------------------------------------------------------------
# plan:facets → 逐库查询计划
# ---------------------------------------------------------------------------
def load_facets(args, work_dir):
    """facets 来自 --facets 或 work/facets.json;缺失返回 None。"""
    path = getattr(args, "facets", None) or os.path.join(work_dir, "facets.json")
    if not os.path.isfile(path):
        return None, path
    obj, err, _ = read_json_file(path)
    if err or not isinstance(obj, dict):
        return None, path
    facets = obj.get("facets")
    if not isinstance(facets, list) or not facets:
        return None, path
    obj["_loaded_from"] = path
    return obj, path


def facet_terms(facets):
    return [t for f in facets for t in (f.get("terms") or []) if t]


def build_crossref_plan(facets, tw, ptypes):
    terms = facet_terms(facets)
    filters = []
    if tw.get("from"):
        filters.append("from-pub-date:%s" % tw["from"])
    if tw.get("to"):
        filters.append("until-pub-date:%s" % tw["to"])
    for pt in ptypes:
        filters.append("type:%s" % pt)
    params = {
        "query.bibliographic": " ".join(terms),
        "filter": ",".join(filters) if filters else None,
        "rows": DB_CAPABILITIES["crossref"]["default_rows"],
        "offset": 0,
        "sort": "relevance",
        "select": ["DOI", "title", "author", "published", "container-title", "type"],
    }
    return params


def build_europepmc_plan(facets, tw):
    blocks = []
    for f in facets:
        terms = [t for t in (f.get("terms") or []) if t]
        if not terms:
            continue
        blocks.append("(" + " OR ".join('TITLE_ABS:"%s"' % t for t in terms) + ")")
    q = " AND ".join(blocks)
    if tw.get("from") or tw.get("to"):
        y_from = (tw.get("from") or "1900")[:4]
        y_to = (tw.get("to") or "2999")[:4]
        q = (q + " AND " if q else "") + "PUB_YEAR:[%s TO %s]" % (y_from, y_to)
    params = {
        "query": q,
        "format": "json",
        "pageSize": DB_CAPABILITIES["europepmc"]["default_page_size"],
        "cursorMark": "*",
        "sort": "",
    }
    return params


def build_publisher_plan(facets, tw):
    return {
        "keywords": facet_terms(facets),
        "time_window": {k: v for k, v in tw.items() if v},
        "note": "出版方站点语法不保证公开;以中性关键词块登记检索意图,"
                "实际语法需按目标站点另行适配;本计划仅作调度登记",
    }


def coverage_role(db, facets):
    cap = DB_CAPABILITIES.get(db, {})
    strong, weak = [], []
    if db == "crossref":
        strong = [f.get("id") for f in facets if f.get("id")]
    elif db == "europepmc":
        for f in facets:
            toks = set(tokenize(" ".join(f.get("terms") or [])))
            if toks & BIOMED_WEAK_HINTS:
                weak.append(f.get("id"))
            else:
                strong.append(f.get("id"))
    else:  # publisher
        strong = [f.get("id") for f in facets if f.get("role") in
                  ("intervention", "context") and f.get("id")]
    return {
        "strong_on": sorted(x for x in strong if x),
        "weak_on": sorted(x for x in weak if x),
        "strength_note": cap.get("strength", ""),
        "weakness_note": cap.get("weakness", ""),
    }


def degradation_chain(db, role):
    lost = role["strong_on"] or []
    impact = ("facet %s 失去该库覆盖" % ",".join(lost)) if lost else "该库无核心 facet 承担"
    return ("若 %s 响应缺失:不臆造、不跳过——在 coverage_declaration 登记 gap,"
            "%s;result.status 降级为 partial 并在 uncertainty 中声明" % (db, impact))


def cmd_plan(args):
    work_dir = args.work
    summary_path = os.path.join(work_dir, "case_summary.json")
    summary, err, _ = read_json_file(summary_path)
    if err or not isinstance(summary, dict):
        print("[plan] FATAL: 缺少 %s(先运行 parse)" % summary_path, file=sys.stderr)
        return EXIT_BAD_INPUT

    facets_obj, facets_path = load_facets(args, work_dir)
    if facets_obj is None:
        print("[plan] 诚实降级: facets.json 缺失或非法(%s)。"
              "facets 是模型判断步骤的产物,脚本不臆造研究切面;"
              "请由模型完成切面抽取后写入该路径再重跑 plan。" % facets_path,
              file=sys.stderr)
        return EXIT_DEGRADED

    facets = facets_obj.get("facets") or []
    tw = facets_obj.get("time_window") or {}
    ptypes = facets_obj.get("publication_types") or ["journal-article"]

    # source set:需要 case.json;从 summary 反查 input 不可得,故直接重读
    case_path = os.path.join(args.input, "case.json") if getattr(args, "input", None) else None
    source_dbs = None
    if case_path and os.path.isfile(case_path):
        case, _ = load_case(args.input)
        if case:
            source_dbs = extract_source_dbs(case, summary.get("files", []))
    if not source_dbs:
        source_dbs = extract_source_dbs({}, summary.get("files", []))

    cap_ref_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "references", "db-capabilities.md")
    cap_ref_note = {"path": "references/db-capabilities.md", "sha256": None,
                    "status": "embedded-constants-only"}
    if os.path.isfile(cap_ref_path):
        cap_ref_note["sha256"] = sha256_file(cap_ref_path)
        cap_ref_note["status"] = "constants-transcribed-from-file(sha256 已核对)"

    builders = {"crossref": lambda: build_crossref_plan(facets, tw, ptypes),
                "europepmc": lambda: build_europepmc_plan(facets, tw),
                "publisher": lambda: build_publisher_plan(facets, tw)}
    plans = []
    for db in source_dbs:
        cap = DB_CAPABILITIES.get(db)
        if cap is None:
            plans.append({"db": db, "planned": False,
                          "note": "能力表无此库条目,无法编译查询计划",
                          "planned_query": None})
            continue
        params = builders[db]() if db in builders else {}
        role = coverage_role(db, facets)
        planned_query = (params.get("query.bibliographic") or params.get("query")
                         or " ".join(params.get("keywords") or []))
        plans.append({
            "db": db,
            "planned": True,
            "planned_query": planned_query,
            "query_params": params,
            "pagination": {"style": cap["pagination"],
                           "page_size": cap.get("default_page_size") or cap.get("default_rows"),
                           "start": ("cursorMark=*" if db == "europepmc"
                                     else "offset=0" if db == "crossref"
                                     else "n/a(导出/站点翻页)")},
            "sort": cap["sort"][0] if cap.get("sort") else None,
            "quota_policy": cap["quota"],
            "coverage_role": role,
            "degradation_chain": degradation_chain(db, role),
        })

    plan_doc = {
        "case_id": summary.get("case_id"),
        "facets_source": os.path.basename(facets_obj.get("_loaded_from", "facets.json")),
        "facets": facets,
        "time_window": tw,
        "capability_reference": cap_ref_note,
        "offline_notice": "本计划仅供离线调度登记;评测环境无网络,绝不发起实时 API 调用",
        "plans": plans,
    }
    write_json(os.path.join(work_dir, "query_plan.json"), plan_doc)
    print("[plan] source_dbs=%s plans=%d" % (",".join(source_dbs), len(plans)))
    return EXIT_OK


# ---------------------------------------------------------------------------
# reconcile:计划 vs 在场材料
# ---------------------------------------------------------------------------
DB_TO_TYPES = {"crossref": {"crossref"}, "europepmc": {"europepmc"},
               "publisher": {"publisher_json", "publisher_jsonl", "publisher_csv"}}


def extract_echo(obj, db):
    if db == "crossref":
        q = obj.get("message", {}).get("query")
        if isinstance(q, dict):
            return " ".join(str(v) for v in q.values() if v)
        if isinstance(q, str):
            return q
        return None
    if db == "europepmc":
        req = obj.get("request")
        if isinstance(req, dict) and req.get("queryString"):
            return str(req["queryString"])
        if obj.get("queryString"):
            return str(obj["queryString"])
        return None
    return None


def echo_status(planned_query, echo_text):
    if echo_text is None:
        return "not_echoed", 0.0
    planned_tokens = set(tokenize(planned_query))
    if not planned_tokens:
        return "not_echoed", 0.0
    echo_tokens = set(tokenize(echo_text))
    overlap = len(planned_tokens & echo_tokens) / float(len(planned_tokens))
    if overlap >= 0.6:
        return "matched", round(overlap, 3)
    return "mismatched", round(overlap, 3)


def extract_candidates(obj, stype, db):
    """从在场响应中抽取候选标识(不去重、不合并,仅登记来源)。"""
    out = []
    records = []
    if stype == "crossref":
        records = obj.get("message", {}).get("items") or []
        for it in records:
            if isinstance(it, dict):
                title = it.get("title")
                out.append({"source_db": db,
                            "identifier": it.get("DOI"),
                            "title": (title[0] if isinstance(title, list) and title
                                      else title)})
    elif stype == "europepmc":
        records = obj.get("resultList", {}).get("result") or []
        for it in records:
            if isinstance(it, dict):
                out.append({"source_db": db,
                            "identifier": it.get("doi") or
                            ("PMID:%s" % it.get("pmid") if it.get("pmid") else None),
                            "title": it.get("title")})
    elif stype in ("publisher_json", "publisher_jsonl", "publisher_csv"):
        if isinstance(obj, list):
            records = obj
        elif isinstance(obj, dict):
            for key in ("records", "articles", "results", "items", "publications"):
                if isinstance(obj.get(key), list):
                    records = obj[key]
                    break
        for it in records:
            if isinstance(it, dict):
                out.append({"source_db": db,
                            "identifier": it.get("doi") or it.get("DOI"),
                            "title": it.get("title") or it.get("Title")})
    return [c for c in out if c.get("identifier") or c.get("title")]


def cmd_reconcile(args):
    work_dir = args.work
    input_dir = args.input
    summary, err, _ = read_json_file(os.path.join(work_dir, "case_summary.json"))
    if err or not isinstance(summary, dict):
        print("[reconcile] FATAL: 缺少 case_summary.json(先运行 parse)", file=sys.stderr)
        return EXIT_BAD_INPUT
    plan_doc, err, _ = read_json_file(os.path.join(work_dir, "query_plan.json"))
    if err or not isinstance(plan_doc, dict):
        print("[reconcile] FATAL: 缺少 query_plan.json(先运行 plan)", file=sys.stderr)
        return EXIT_BAD_INPUT

    by_type = {}
    for f in summary.get("files", []):
        if f.get("present"):
            by_type.setdefault(f.get("sniffed_type"), []).append(f)

    dbs_report, gaps, ledger, candidates = [], [], [], []
    seq = 0
    for p in plan_doc.get("plans", []):
        db = p.get("db")
        seq += 1
        if not p.get("planned"):
            dbs_report.append({"db": db, "response_present": "absent",
                               "query_echo": "not_echoed",
                               "note": p.get("note", "未计划")})
            continue
        types = DB_TO_TYPES.get(db, set())
        matched_files = []
        for t in sorted(types):
            matched_files.extend(by_type.get(t, []))
        planned_query = p.get("planned_query") or ""
        if not matched_files:
            role = p.get("coverage_role") or {}
            impact_facets = role.get("strong_on") or []
            gap = {
                "db": db,
                "planned_query": planned_query,
                "impact": {"facets_losing_coverage": impact_facets,
                           "detail": ("%s 响应缺失,上述 facet 仅由其余在场库支撑"
                                      % db) if impact_facets else
                                     ("%s 响应缺失;该库不承担核心 facet,影响有限" % db)},
                "declaration": ("诚实声明: 计划中包含数据库 %s,但输入材料中不存在其响应文件;"
                                "本技能不臆造该库结果,相关覆盖按缺口登记。" % db),
            }
            gaps.append(gap)
            dbs_report.append({"db": db, "response_present": "absent",
                               "query_echo": "not_echoed",
                               "gap": gap["declaration"]})
            ledger.append({"seq": seq, "db": db, "planned_query": planned_query,
                           "params": p.get("query_params"),
                           "pagination": p.get("pagination"),
                           "response_present": False, "query_echo": "not_echoed",
                           "echo_overlap": 0.0, "result_count": 0,
                           "truncation_detected": False})
            continue

        # 响应在场:取首个匹配文件核对回响
        f0 = matched_files[0]
        obj, jerr, _ = read_json_file(os.path.join(input_dir, f0["path"])) \
            if f0["sniffed_type"] in ("crossref", "europepmc") else (None, None, None)
        echo_txt = extract_echo(obj, db) if obj else None
        status, overlap = echo_status(planned_query, echo_txt)
        dbs_report.append({
            "db": db, "response_present": "present",
            "material_files": [f["path"] for f in matched_files],
            "query_echo": status, "echo_overlap": overlap,
            "echo_text": echo_txt,
            "result_count": sum(f.get("record_count", 0) for f in matched_files),
            "truncation_detected": any(f.get("truncation_detected")
                                       for f in matched_files),
            "truncation_detail": next((f.get("truncation_detail")
                                       for f in matched_files
                                       if f.get("truncation_detected")), None),
        })
        ledger.append({"seq": seq, "db": db, "planned_query": planned_query,
                       "params": p.get("query_params"),
                       "pagination": p.get("pagination"),
                       "response_present": True, "query_echo": status,
                       "echo_overlap": overlap,
                       "result_count": sum(f.get("record_count", 0)
                                           for f in matched_files),
                       "truncation_detected": any(f.get("truncation_detected")
                                                  for f in matched_files)})
        # 候选登记(不去重)
        for f in matched_files:
            o2, e2, _ = read_json_file(os.path.join(input_dir, f["path"]))
            if e2 is None:
                candidates.extend(extract_candidates(o2, f["sniffed_type"], db))

    truncation_flags = [{"db": d["db"], "detail": d.get("truncation_detail")}
                        for d in dbs_report if d.get("truncation_detected")]
    declaration = {
        "case_id": plan_doc.get("case_id"),
        "summary": ("计划库 %d 个;响应在场 %d 个;缺口 %d 个;截断告警 %d 个"
                    % (len(plan_doc.get("plans", [])),
                       sum(1 for d in dbs_report if d["response_present"] == "present"),
                       len(gaps), len(truncation_flags))),
        "dbs": dbs_report,
        "gaps": gaps,
        "truncation_flags": truncation_flags,
        "quarantined_materials": summary.get("unknown_or_quarantined", []),
        "missing_declared_materials": summary.get("missing_declared_materials", []),
        "honesty_notice": ("本声明仅基于离线材料与查询计划的对账;缺失库的结果"
                           "绝不由模型臆造补齐。"),
    }
    write_json(os.path.join(work_dir, "coverage_declaration.json"), declaration)
    write_jsonl(os.path.join(work_dir, "query_ledger.jsonl"), ledger)
    write_json(os.path.join(work_dir, "candidate_pool.json"),
               {"note": "在场响应中的候选标识,未去重未合并,供下游使用",
                "candidates": candidates})
    print("[reconcile] present=%d gaps=%d truncations=%d ledger_lines=%d"
          % (sum(1 for d in dbs_report if d["response_present"] == "present"),
             len(gaps), len(truncation_flags), len(ledger)))
    return EXIT_OK


# ---------------------------------------------------------------------------
# finalize
# ---------------------------------------------------------------------------
def fill_candidate_set(ctx):
    pool = ctx.get("candidate_pool") or {}
    return pool.get("candidates") or []


def fill_coverage_summary(ctx):
    dec = ctx.get("coverage_declaration") or {}
    return {"summary": dec.get("summary"),
            "gaps": [g.get("db") for g in dec.get("gaps", [])],
            "truncation_flags": dec.get("truncation_flags", [])}


def fill_ledger_pointer(ctx):
    return "query_ledger.jsonl"


def fill_plan_pointer(ctx):
    return "query_plan.json"


def fill_open_questions(ctx):
    dec = ctx.get("coverage_declaration") or {}
    qs = []
    for g in dec.get("gaps", []):
        qs.append("数据库 %s 的响应缺失:需补采该库材料后重跑,或接受该覆盖缺口。"
                  % g.get("db"))
    for t in dec.get("truncation_flags", []):
        qs.append("数据库 %s 的响应为单页截断(%s):如需全量候选需补采后续分页。"
                  % (t.get("db"), t.get("detail")))
    return qs


def fill_status_report(ctx):
    return {"status": ctx.get("status"), "status_reason": ctx.get("status_reason"),
            "checks": ctx.get("checks")}


def fill_method_notes(ctx):
    return ("方法说明: 本结果由 query-orchestration-planner 生成——研究问题先由模型抽取为"
            "中性 facet 概念块(facets.json),脚本再按各库语法/分页/配额编译查询计划,"
            "并与在场离线材料对账;缺失库显式声明缺口,截断响应显式标记。"
            "候选集为在场响应的原始标识登记,未去重未合并;证据抽取、去重与综述"
            "属下游技能职责。")


CONTRACT_FILLERS = {
    "fill_candidate_set": fill_candidate_set,
    "fill_coverage_summary": fill_coverage_summary,
    "fill_ledger_pointer": fill_ledger_pointer,
    "fill_plan_pointer": fill_plan_pointer,
    "fill_open_questions": fill_open_questions,
    "fill_status_report": fill_status_report,
    "fill_method_notes": fill_method_notes,
}


def decide_status(declaration, unresolved, parse_rc, plan_rc, reconcile_rc):
    if parse_rc == EXIT_BAD_INPUT:
        return "failed", "case.json 缺失或非法,无法开展编排"
    reasons = []
    if plan_rc == EXIT_DEGRADED:
        reasons.append("facets.json 缺失,查询计划未编译")
    if reconcile_rc == EXIT_BAD_INPUT:
        reasons.append("对账阶段输入缺失")
    gaps = (declaration or {}).get("gaps", [])
    truncs = (declaration or {}).get("truncation_flags", [])
    if gaps:
        reasons.append("数据库缺口: %s" % ",".join(g.get("db") for g in gaps))
    if truncs:
        reasons.append("截断告警: %s" % ",".join(t.get("db") for t in truncs))
    if unresolved:
        reasons.append("契约字段未填充: %s" % ",".join(u.get("field") for u in unresolved))
    if reasons:
        return "partial", ";".join(reasons)
    return "complete", "全部计划库响应在场且契约字段均已填充"


def cmd_finalize(args):
    work_dir, output_dir = args.work, args.output
    os.makedirs(output_dir, exist_ok=True)

    case, case_err = load_case(args.input)
    if case_err:
        # 输入非法:仍尽力写出最小 result.json
        minimal = {"case_id": None, "skill_name": SKILL_NAME,
                   "status": "failed",
                   "status_reason": "输入非法: %s" % case_err,
                   "unresolved": [], "uncertainty": [case_err]}
        try:
            write_json(os.path.join(output_dir, "result.json"), minimal)
        except OSError:
            pass
        print("[finalize] FATAL: %s" % case_err, file=sys.stderr)
        return EXIT_BAD_INPUT

    contract_fields = extract_contract_fields(case)

    ctx = {}
    for name, fname in (("summary", "case_summary.json"),
                        ("plan", "query_plan.json"),
                        ("coverage_declaration", "coverage_declaration.json"),
                        ("candidate_pool", "candidate_pool.json")):
        obj, _e, _ = read_json_file(os.path.join(work_dir, fname))
        ctx[name] = obj if isinstance(obj, dict) else None
    checks_obj, _e, _ = read_json_file(os.path.join(work_dir, "stage_checks.json"))
    checks = checks_obj.get("checks") if isinstance(checks_obj, dict) else None
    if not checks:
        checks = {"parse": "unknown", "plan": "unknown",
                  "reconcile": "unknown", "note": "standalone finalize,无 run-all 阶段记录"}
    checks = dict(checks)
    checks["finalize"] = EXIT_OK

    declaration = ctx.get("coverage_declaration")
    # 先以空 unresolved 估状态,填充后再精化
    status, status_reason = decide_status(
        declaration, [], checks.get("parse", 0) if isinstance(checks.get("parse"), int) else 0,
        checks.get("plan", 0) if isinstance(checks.get("plan"), int) else 0,
        checks.get("reconcile", 0) if isinstance(checks.get("reconcile"), int) else 0)
    ctx["status"], ctx["status_reason"], ctx["checks"] = status, status_reason, checks

    filled, unresolved = {}, []
    for field in contract_fields:
        lname = field.lower()
        value, done = None, False
        if any(h in lname for h in DOWNSTREAM_ONLY_HINTS):
            unresolved.append({"field": field,
                               "reason": "该字段属下游(证据/去重/综述)职责,"
                                         "本技能不臆造填充,置 null 登记"})
            filled[field] = None
            continue
        for kw, fname in CONTRACT_FILL_RULES:
            if kw in lname:
                try:
                    value = CONTRACT_FILLERS[fname](ctx)
                    done = True
                except Exception as e:  # noqa: BLE001 — 填充失败不崩溃
                    unresolved.append({"field": field,
                                       "reason": "填充函数异常: %s" % e})
                    value = None
                break
        if not done and not any(u["field"] == field for u in unresolved):
            unresolved.append({"field": field,
                               "reason": "无确定性映射,禁止捏造,置 null 登记"})
            value = None
        filled[field] = value

    # 用真实 unresolved 重估状态
    status, status_reason = decide_status(
        declaration, unresolved,
        checks.get("parse", 0) if isinstance(checks.get("parse"), int) else 0,
        checks.get("plan", 0) if isinstance(checks.get("plan"), int) else 0,
        checks.get("reconcile", 0) if isinstance(checks.get("reconcile"), int) else 0)
    ctx["status"], ctx["status_reason"] = status, status_reason

    # 搬运核心产物到 output
    products = {}
    for fname in ("query_plan.json", "coverage_declaration.json", "query_ledger.jsonl"):
        src = os.path.join(work_dir, fname)
        if os.path.isfile(src):
            dst = os.path.join(output_dir, fname)
            with open(src, "rb") as fi, open(dst, "wb") as fo:
                fo.write(fi.read())
            products[os.path.splitext(fname)[0]] = fname
        else:
            products[os.path.splitext(fname)[0]] = None

    sources = []
    for f in (ctx.get("summary") or {}).get("files", []):
        sources.append({"path": f.get("path"), "sha256": f.get("sha256"),
                        "sniffed_type": f.get("sniffed_type"),
                        "record_count": f.get("record_count"),
                        "truncation_detected": f.get("truncation_detected")})

    uncertainty = []
    for g in (declaration or {}).get("gaps", []):
        uncertainty.append({"kind": "absent_db", "detail": g.get("declaration")})
    for t in (declaration or {}).get("truncation_flags", []):
        uncertainty.append({"kind": "truncation",
                            "detail": "%s: %s" % (t.get("db"), t.get("detail"))})
    for q in (declaration or {}).get("quarantined_materials", []):
        uncertainty.append({"kind": "unknown_format",
                            "detail": "材料 %s 格式未知,已隔离登记" % q})
    for m in (declaration or {}).get("missing_declared_materials", []):
        uncertainty.append({"kind": "missing_declared",
                            "detail": "case.json 声明的材料 %s 磁盘缺失" % m})
    if (ctx.get("plan") or {}).get("capability_reference", {}).get("status") == \
            "embedded-constants-only":
        uncertainty.append({"kind": "unconfirmed_assumption",
                            "detail": "references/db-capabilities.md 未定位,"
                                      "能力事实仅来自脚本内嵌常量"})

    counts = {
        "materials_total": len(sources),
        "materials_present": sum(1 for s in sources if s.get("sha256")),
        "records_observed": sum(s.get("record_count") or 0 for s in sources),
        "planned_dbs": len((ctx.get("plan") or {}).get("plans", [])),
        "gaps": len((declaration or {}).get("gaps", [])),
        "truncation_flags": len((declaration or {}).get("truncation_flags", [])),
        "candidates_registered": len((ctx.get("candidate_pool") or {}).get("candidates", [])),
        "contract_fields": len(contract_fields),
        "contract_unresolved": len(unresolved),
    }

    seq = 0

    def chg(text):
        nonlocal seq
        seq += 1
        return {"seq": seq, "change": text}

    change_records = [
        chg("parse: 嗅探材料 %d 份(missing=%d, quarantined=%d)"
            % (counts["materials_total"],
               len((ctx.get("summary") or {}).get("missing_declared_materials", [])),
               len((ctx.get("summary") or {}).get("unknown_or_quarantined", [])))),
        chg("plan: 编译查询计划 %d 库" % counts["planned_dbs"]),
        chg("reconcile: 缺口 %d,截断告警 %d,候选登记 %d"
            % (counts["gaps"], counts["truncation_flags"], counts["candidates_registered"])),
        chg("finalize: 契约字段 %d,未决 %d,status=%s"
            % (counts["contract_fields"], counts["contract_unresolved"], status)),
    ]

    result = {
        "case_id": case["case_id"],
        "skill_name": SKILL_NAME,
        "skill_version": SKILL_VERSION,
        "status": status,
        "status_reason": status_reason,
        "product": products,
        "sources": sources,
        "unresolved": unresolved,
        "uncertainty": uncertainty,
        "change_records": change_records,
        "counts": counts,
        "checks": checks,
    }
    # 契约字段顶层展开
    for k, v in filled.items():
        result[k] = v

    write_json(os.path.join(output_dir, "result.json"), result)
    print("[finalize] status=%s unresolved=%d gaps=%d" % (status, len(unresolved),
                                                          counts["gaps"]))
    return EXIT_OK


# ---------------------------------------------------------------------------
# selfcheck
# ---------------------------------------------------------------------------
def cmd_selfcheck(args):
    work_dir, output_dir, input_dir = args.work, args.output, args.input
    failures, passes = [], []

    def check(ok, label):
        (passes if ok else failures).append(label)

    result, err, _ = read_json_file(os.path.join(output_dir, "result.json"))
    check(err is None and isinstance(result, dict), "result.json 存在且可解析")
    if err or not isinstance(result, dict):
        report = {"pass": False, "failures": failures, "passes": passes}
        write_json(os.path.join(work_dir, "selfcheck_report.json"), report)
        print("[selfcheck] FAIL: result.json 不可解析")
        return EXIT_SELFCHECK_FAIL

    case, case_err = load_case(input_dir)
    check(case_err is None, "case.json 可读")
    contract_fields = extract_contract_fields(case) if case else []

    check(bool(result.get("case_id")), "result.json 含 case_id")
    if case:
        check(result.get("case_id") == case.get("case_id"), "case_id 与 case.json 一致")
    missing_keys = [f for f in contract_fields if f not in result]
    check(not missing_keys, "契约字段全部顶层存在(缺失: %s)" % ",".join(missing_keys))

    unresolved_fields = {u.get("field") for u in result.get("unresolved", [])}
    null_not_registered = [f for f in contract_fields
                           if result.get(f) is None and f not in unresolved_fields]
    registered_not_null = [f for f in unresolved_fields if result.get(f) is not None]
    check(not null_not_registered,
          "所有 null 契约字段均已登记 unresolved(漏: %s)" % ",".join(null_not_registered))
    check(not registered_not_null,
          "unresolved 登记字段确为 null(误登记: %s)" % ",".join(registered_not_null))

    # 产物哈希一致
    for key, fname in (result.get("product") or {}).items():
        if fname is None:
            failures.append("产物 %s 缺失" % key)
            continue
        p = os.path.join(output_dir, fname)
        check(os.path.isfile(p), "产物 %s 存在于 output" % fname)
        if os.path.isfile(p):
            wp = os.path.join(work_dir, fname)
            if os.path.isfile(wp):
                check(sha256_file(p) == sha256_file(wp),
                      "产物 %s 与 work 副本哈希一致" % fname)

    # 计数可重算
    summary, _e, _ = read_json_file(os.path.join(work_dir, "case_summary.json"))
    if isinstance(summary, dict):
        files = summary.get("files", [])
        c = result.get("counts") or {}
        check(c.get("materials_total") == len(files), "counts.materials_total 可重算")
        check(c.get("records_observed") ==
              sum(f.get("record_count") or 0 for f in files),
              "counts.records_observed 可重算")
        # 无静默丢弃:在场+缺失+隔离 = 声明+额外
        check(summary.get("counts", {}).get("declared", -1) +
              summary.get("counts", {}).get("undeclared_extra", -1) == len(files),
              "所有材料均被登记,无静默丢弃")
    else:
        failures.append("case_summary.json 缺失,无法重算计数")

    dec, _e, _ = read_json_file(os.path.join(work_dir, "coverage_declaration.json"))
    if isinstance(dec, dict):
        gap_dbs = {g.get("db") for g in dec.get("gaps", [])}
        unc_dbs = set()
        for u in result.get("uncertainty", []):
            if u.get("kind") == "absent_db":
                for db in gap_dbs:
                    if db and db in (u.get("detail") or ""):
                        unc_dbs.add(db)
        check(gap_dbs <= unc_dbs or not gap_dbs,
              "每个缺口库均在 result.json uncertainty 中声明")
        # 台账行数 = 计划库数
        ledger_path = os.path.join(output_dir, "query_ledger.jsonl")
        if os.path.isfile(ledger_path):
            with io.open(ledger_path, "r", encoding="utf-8") as f:
                n_lines = sum(1 for ln in f if ln.strip())
            plan, _e2, _ = read_json_file(os.path.join(work_dir, "query_plan.json"))
            n_plans = len((plan or {}).get("plans", [])) if isinstance(plan, dict) else -1
            check(n_lines == n_plans, "台账行数(%d)=计划库数(%d)" % (n_lines, n_plans))
    else:
        failures.append("coverage_declaration.json 缺失")

    ok = not failures
    report = {"pass": ok, "failures": failures, "passes": passes}
    write_json(os.path.join(work_dir, "selfcheck_report.json"), report)
    print("[selfcheck] %s: %d pass, %d fail" % ("PASS" if ok else "FAIL",
                                                len(passes), len(failures)))
    for f_ in failures:
        print("  FAIL: %s" % f_)
    return EXIT_OK if ok else EXIT_SELFCHECK_FAIL


# ---------------------------------------------------------------------------
# run-all
# ---------------------------------------------------------------------------
def cmd_run_all(args):
    checks = {}
    rc = cmd_parse(args)
    checks["parse"] = rc
    if rc == EXIT_BAD_INPUT:
        # 仍尝试 minimal result.json
        try:
            cmd_finalize(args)
        except Exception:  # noqa: BLE001
            pass
        print("[run-all] 输入非法,退出码 3", file=sys.stderr)
        return EXIT_BAD_INPUT

    rc_plan = cmd_plan(args)
    checks["plan"] = rc_plan
    if rc_plan == EXIT_OK:
        checks["reconcile"] = cmd_reconcile(args)
    else:
        checks["reconcile"] = "skipped(plan 降级)"
    write_json(os.path.join(args.work, "stage_checks.json"), {"checks": checks})

    checks["finalize"] = cmd_finalize(args)
    write_json(os.path.join(args.work, "stage_checks.json"), {"checks": checks})
    rc_self = cmd_selfcheck(args)
    checks["selfcheck"] = rc_self
    write_json(os.path.join(args.work, "stage_checks.json"), {"checks": checks})
    print("[run-all] 完成: %s" % json.dumps(checks, ensure_ascii=False))
    return EXIT_OK if rc_self == EXIT_OK else EXIT_SELFCHECK_FAIL


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def build_parser():
    p = argparse.ArgumentParser(
        prog="query_planner.py",
        description="多数据库联合检索的上游查询编排与来源调度引擎(离线、确定性、诚实降级)。"
                    "退出码: 0=正常 1=自查未通过 2=诚实降级(如 facets 缺失) 3=输入非法。")
    sub = p.add_subparsers(dest="command")

    def add_io(sp, need_output=False, need_facets=False):
        sp.add_argument("--input", default="/input", help="输入目录(含 case.json/task.md/materials)")
        sp.add_argument("--work", default="/app/work", help="中间产物目录")
        if need_output:
            sp.add_argument("--output", default="/app/output", help="交付目录")
        if need_facets:
            sp.add_argument("--facets", default=None,
                            help="模型产出的 facets.json 路径(缺省取 work/facets.json)")

    sp = sub.add_parser("parse", help="读取 case+task,嗅探材料 → case_summary.json")
    add_io(sp)
    sp.set_defaults(func=cmd_parse)

    sp = sub.add_parser("plan", help="facets.json → 逐库 query_plan.json(facets 缺失退出码 2)")
    add_io(sp, need_facets=True)
    sp.set_defaults(func=cmd_plan)

    sp = sub.add_parser("reconcile", help="计划 vs 在场材料 → coverage_declaration.json + query_ledger.jsonl")
    add_io(sp)
    sp.set_defaults(func=cmd_reconcile)

    sp = sub.add_parser("finalize", help="汇总 result.json(契约字段全登记,缺失置 null)")
    add_io(sp, need_output=True)
    sp.set_defaults(func=cmd_finalize)

    sp = sub.add_parser("selfcheck", help="交付前自查(契约/哈希/计数/无静默丢弃),退出码 0/1")
    add_io(sp, need_output=True)
    sp.set_defaults(func=cmd_selfcheck)

    sp = sub.add_parser("run-all", help="parse→plan→reconcile→finalize→selfcheck 顺序编排")
    add_io(sp, need_output=True, need_facets=True)
    sp.set_defaults(func=cmd_run_all)
    return p


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return EXIT_OK
    try:
        return int(args.func(args))
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001 — 顶层兜底,绝不裸崩溃
        print("[query_planner] 未预期异常(已兜底): %r" % e, file=sys.stderr)
        try:
            out = getattr(args, "output", None)
            if out:
                os.makedirs(out, exist_ok=True)
                write_json(os.path.join(out, "result.json"),
                           {"case_id": None, "skill_name": SKILL_NAME,
                            "status": "failed",
                            "status_reason": "内部异常: %r" % e,
                            "unresolved": [], "uncertainty": ["internal:%r" % e]})
        except Exception:  # noqa: BLE001
            pass
        return EXIT_BAD_INPUT


if __name__ == "__main__":
    sys.exit(main())
