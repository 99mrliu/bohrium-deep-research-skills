#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
coverage_cartographer.py — 覆盖制图师（Coverage Cartographer）

多数据库联合检索场景的「覆盖完备性审计与缺口诚实化」脚本。

设计原则：交付物必须精确说明——哪些数据库、哪些字段被覆盖；哪些文献仅存在于
单一来源；哪些缺口是系统性的。任何异常都不得被静默吞没，而是落入带类型、带
证据定位、带影响陈述的缺口台账（gap_ledger.json）。

能力阈值表（各库检索语法、字段能力、分页限制）镜像自 references/db-capabilities.md；
缺口类型、严重级与影响陈述模板镜像自 references/gap-taxonomy.md。
两份参考文档为人类可读的权威说明，本脚本内嵌其机器可执行的等价规则。

约束：Python 3 标准库；无网络；无随机性；产出物不含墙钟时间；完全确定、可幂等重跑。

出口码：
  0 = 审计正常完成（分析性缺口如实反映在 status 与各产出物中）；
  2 = 诚实降级（脚本级异常被捕获，或存在无法填充的契约字段）；
  3 = 输入无效（case.json 缺失或不可解析）。
"""
import argparse
import json
import os
import re
import sys
import traceback

# ---------------------------------------------------------------------------
# 常量：规范字段、已知数据库、语法差异矩阵（镜像 references/db-capabilities.md）
# ---------------------------------------------------------------------------

CANONICAL_FIELDS = [
    "doi", "pmid", "pmcid", "title", "authors", "journal",
    "year", "volume", "issue", "pages", "abstract", "reference_list",
]

KNOWN_DBS = ["crossref", "europepmc", "publisher"]

# 两库检索语法是否不同（逐字复制同一检索式是否有意义损失）。
# 依据 references/db-capabilities.md：crossref 使用 query.bibliographic 自由文本参数；
# europepmc 使用自有查询语言（字段标签 TITLE:/AUTH:/PUB_YEAR: 等）；
# publisher 端点各异、无统一语法。三者两两不同。
DB_SYNTAX_DIFFERS = {
    ("crossref", "europepmc"): True,
    ("crossref", "publisher"): True,
    ("europepmc", "publisher"): True,
}

# ---------------------------------------------------------------------------
# 缺口类型规格：严重级 + 影响陈述模板（镜像 references/gap-taxonomy.md）
# ---------------------------------------------------------------------------

ENTRY_SPECS = {
    "db_absent": {
        "severity": "critical",
        "impact": "期望数据库 {db} 没有任何可用材料：该库本应命中的文献整体不可见，"
                  "候选集对该库系统性缺失，用户不能断言检索覆盖了 {db}。",
    },
    "extra_source": {
        "severity": "info",
        "impact": "材料来源 {db} 不在期望数据库集合中：其记录已纳入审计，"
                  "但是否应当采信需用户确认。",
    },
    "mechanical_copy": {
        "severity": "warning",
        "impact": "同一检索式被逐字发送至语法能力不同的数据库（{dbs}）："
                  "各库的字段检索能力未被利用，召回可能系统性偏低或偏离预期。",
    },
    "query_evidence_missing": {
        "severity": "info",
        "impact": "数据库 {db} 缺少检索式/请求参数证据：无法复核其检索编排是否合理，"
                  "该库覆盖度无法归因，用户不能断言检索是按预期执行的。",
    },
    "hitcount_mismatch": {
        "severity": "warning",
        "impact": "{db} 声明命中总数 {declared}，实际返回 {returned} 条，"
                  "且无翻页/游标证据：未返回部分不可见，用户不能断言已覆盖全部命中。",
    },
    "empty_response": {
        "severity": "warning",
        "impact": "{db} 返回 0 条记录：无法区分「确实无命中」与「检索式/接口问题」，"
                  "需人工复核后才能下结论。",
    },
    "envelope_malformed": {
        "severity": "critical",
        "impact": "材料 {file} 无法解析：其内容整体缺失，相关来源的覆盖结论不可用。",
    },
    "material_missing": {
        "severity": "critical",
        "impact": "案例清单声明的材料 {file} 不存在：对应内容缺失，相关来源无法审计。",
    },
    "unclassified_material": {
        "severity": "warning",
        "impact": "材料 {file} 的结构无法归类为任何已知来源类型：已跳过，"
                  "其潜在贡献未计入候选集与覆盖矩阵。",
    },
    "field_systematic_gap": {
        "severity": "warning",
        "impact": "字段 {field} 在 {db} 的 {count} 条记录中 0 次提供：跨库合并时"
                  "该字段对 {db} 系统性缺失，用户不能据此字段比较或筛选该库记录。",
    },
    "identifier_conflict": {
        "severity": "warning",
        "impact": "标识符 {identifier} 在不同来源间元数据冲突（{detail}）："
                  "已列出待仲裁、未静默合并；仲裁前用户不能确信其规范元数据。",
    },
    "import_state_gap": {
        "severity": "warning",
        "impact": "增量导入状态与检索响应不一致（{direction}：{identifier}）："
                  "导入集与检索集存在偏差，用户不能断言二者一致。",
    },
    "referenced_not_retrieved": {
        "severity": "warning",
        "impact": "引用图节点 {node} 未被任何来源检索到：引文追踪存在断点，"
                  "被引/引用文献可能遗漏，用户不能断言引用网络已闭合。",
    },
    "single_source_only": {
        "severity": "info",
        "impact": "文献 {identity} 仅出现于 {db}：无第二来源交叉验证，"
                  "其存在性与元数据可信度依赖单一来源。",
    },
}

SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2}


# ---------------------------------------------------------------------------
# 基础工具
# ---------------------------------------------------------------------------

def write_json(path, obj):
    """确定性 JSON 写出：键排序、UTF-8、固定缩进、结尾换行。"""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True))
        fh.write("\n")


def write_text(path, text):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def read_text(path):
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def norm_doi(value):
    """DOI 归一化：小写、去解析前缀与 doi: 前缀、去空白。"""
    if value is None:
        return None
    s = str(value).strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/",
                   "https://dx.doi.org/", "http://dx.doi.org/", "doi:"):
        if s.startswith(prefix):
            s = s[len(prefix):]
    s = s.strip().strip(".")
    return s or None


def norm_title(value):
    """标题归一化：小写、折叠空白、去标点（保留中英文字符与数字）。"""
    if value is None:
        return None
    s = re.sub(r"\s+", " ", str(value)).strip().lower()
    s = re.sub(r"[^0-9a-z一-鿿 ]", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s or None


def norm_year(value):
    if value is None or value == "":
        return None
    m = re.search(r"(19|20)\d{2}", str(value))
    return m.group(0) if m else None


def comp_key(record):
    """复合身份键：归一化标题 | 年份 | 第一作者姓。用于无 DOI 记录的跨源对齐。"""
    t = norm_title(record.get("title"))
    y = norm_year(record.get("year"))
    f = record.get("first_author_family")
    if t and (y or f):
        return "%s|%s|%s" % (t, y or "-", (f or "-").lower())
    return None


# ---------------------------------------------------------------------------
# 各来源记录抽取器：产出统一的最小规范化记录
# ---------------------------------------------------------------------------

def _empty_record(source_db, source_file, index):
    rec = {"source_db": source_db, "source_file": source_file, "index": index,
           "first_author_family": None}
    for field in CANONICAL_FIELDS:
        rec[field] = None
    return rec


def _finalize(rec):
    """计算该记录实际提供了哪些规范字段。"""
    provided = []
    for field in CANONICAL_FIELDS:
        v = rec.get(field)
        if v is None:
            continue
        if isinstance(v, (list, dict)) and not v:
            continue
        if isinstance(v, str) and not v.strip():
            continue
        provided.append(field)
    rec["provided_fields"] = provided
    rec["doi"] = norm_doi(rec.get("doi"))
    rec["year"] = norm_year(rec.get("year"))
    return rec


def from_crossref(item, source_file, index):
    rec = _empty_record("crossref", source_file, index)
    rec["doi"] = item.get("DOI") or item.get("doi")
    titles = item.get("title") or []
    rec["title"] = titles[0] if isinstance(titles, list) and titles else (
        titles if isinstance(titles, str) else None)
    authors, family = [], None
    for a in item.get("author") or []:
        if isinstance(a, dict):
            fam = a.get("family") or ""
            giv = a.get("given") or ""
            disp = (fam + ", " + giv).strip(", ").strip()
            if disp:
                authors.append(disp)
            if family is None and fam:
                family = fam
        elif a:
            authors.append(str(a))
    if family is None and authors:
        family = authors[0].split(",")[0].split()[0]
    rec["authors"] = authors or None
    rec["first_author_family"] = family
    containers = item.get("container-title") or []
    rec["journal"] = containers[0] if isinstance(containers, list) and containers else None
    issued = item.get("issued") or {}
    parts = issued.get("date-parts") or []
    if parts and parts[0]:
        rec["year"] = parts[0][0]
    rec["volume"] = item.get("volume")
    rec["issue"] = item.get("issue")
    rec["pages"] = item.get("page")
    rec["abstract"] = item.get("abstract")
    refs = item.get("reference") or []
    rec["reference_list"] = [
        (r.get("DOI") or r.get("key") or "") for r in refs if isinstance(r, dict)
    ] or None
    return _finalize(rec)


def from_europepmc(item, source_file, index):
    rec = _empty_record("europepmc", source_file, index)
    rec["doi"] = item.get("doi")
    rec["pmid"] = item.get("pmid")
    rec["pmcid"] = item.get("pmcid")
    rec["title"] = item.get("title")
    auth_str = item.get("authorString") or ""
    authors = [a.strip() for a in auth_str.split(",") if a.strip()]
    rec["authors"] = authors or None
    family = authors[0].split()[0] if authors else None
    rec["first_author_family"] = family
    journal = item.get("journalTitle")
    if not journal and isinstance(item.get("journalInfo"), dict):
        journal = item["journalInfo"].get("journal", {}).get("title")
    rec["journal"] = journal
    rec["year"] = item.get("pubYear")
    rec["volume"] = item.get("journalVolume") or item.get("volume")
    rec["issue"] = item.get("issue")
    rec["pages"] = item.get("pageInfo")
    rec["abstract"] = item.get("abstractText")
    return _finalize(rec)


def from_publisher(item, source_db, source_file, index):
    """出版商记录无统一 schema，做保守的键名试探。"""
    rec = _empty_record(source_db, source_file, index)
    if not isinstance(item, dict):
        return _finalize(rec)
    rec["doi"] = item.get("doi") or item.get("DOI")
    rec["pmid"] = item.get("pmid")
    rec["pmcid"] = item.get("pmcid")
    rec["title"] = item.get("title")
    raw_authors = item.get("authors") or item.get("author") or []
    if isinstance(raw_authors, str):
        raw_authors = [raw_authors]
    authors, family = [], None
    for a in raw_authors:
        if isinstance(a, dict):
            fam = a.get("family") or a.get("surname") or ""
            giv = a.get("given") or ""
            disp = (fam + ", " + giv).strip(", ").strip() or a.get("name") or ""
            if disp:
                authors.append(disp)
            if family is None and fam:
                family = fam
        elif a:
            authors.append(str(a))
    if family is None and authors:
        family = authors[0].split(",")[0].split()[0]
    rec["authors"] = authors or None
    rec["first_author_family"] = family
    rec["journal"] = item.get("journal") or item.get("journalTitle")
    rec["year"] = item.get("year") or item.get("pubYear")
    rec["volume"] = item.get("volume")
    rec["issue"] = item.get("issue")
    rec["pages"] = item.get("pages") or item.get("page")
    rec["abstract"] = item.get("abstract")
    refs = item.get("reference_list") or item.get("references")
    rec["reference_list"] = list(refs) if isinstance(refs, list) and refs else None
    return _finalize(rec)


# ---------------------------------------------------------------------------
# 材料嗅探分类
# ---------------------------------------------------------------------------

def classify_material(path, text):
    """
    按信封结构嗅探分类。返回 (classification, db_or_none, records, envelope, note)。
    classification ∈ crossref / europepmc / publisher / reference_graph /
                     import_state / unknown / malformed
    """
    name = os.path.basename(path).lower()
    try:
        data = json.loads(text)
    except ValueError:
        # 尝试 JSONL（每行一个 JSON 对象）
        rows = []
        ok = True
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except ValueError:
                ok = False
                break
        if ok and rows and all(isinstance(r, dict) for r in rows):
            db = _db_from_name(name) or "publisher"
            records = [from_publisher(r, db, name, i) for i, r in enumerate(rows)]
            return ("publisher", db, records, None, "jsonl")
        return ("malformed", None, [], None, "not json / not jsonl")

    if isinstance(data, dict):
        message = data.get("message")
        if isinstance(message, dict) and isinstance(message.get("items"), list):
            records = [from_crossref(it, name, i)
                       for i, it in enumerate(message["items"])]
            return ("crossref", "crossref", records, data, None)
        result_list = data.get("resultList")
        if isinstance(result_list, dict) and isinstance(result_list.get("result"), list):
            records = [from_europepmc(it, name, i)
                       for i, it in enumerate(result_list["result"])]
            return ("europepmc", "europepmc", records, data, None)
        if isinstance(data.get("nodes"), list):
            return ("reference_graph", None, [], data, None)
        if isinstance(data.get("imported_ids"), list):
            return ("import_state", None, [], data, None)
        return ("unknown", None, [], data, "dict without known envelope")

    if isinstance(data, list):
        if all(isinstance(r, dict) for r in data):
            db = _db_from_name(name) or "publisher"
            records = [from_publisher(r, db, name, i) for i, r in enumerate(data)]
            return ("publisher", db, records, None, "json array")
        return ("unknown", None, [], data, "array of non-objects")

    return ("unknown", None, [], data, "scalar json")


def _db_from_name(filename):
    for db in KNOWN_DBS:
        if db in filename:
            return db
    return None


# ---------------------------------------------------------------------------
# 检索编排证据抽取
# ---------------------------------------------------------------------------

QUOTED_RE = re.compile(r'"([^"\n]{3,300})"|「([^」\n]{3,300})」')


def extract_query_evidence(case_obj, task_text, envelopes):
    """从 case.json 结构化字段、task.md 文本行、材料信封三处收集检索式证据。"""
    evidence = []  # {"db","query","origin","locator"}
    seen = set()

    def add(db, query, origin, locator):
        key = (db, query, origin, locator)
        if key not in seen:
            seen.add(key)
            evidence.append({"db": db, "query": query,
                             "origin": origin, "locator": locator})

    # (a) case.json 结构化查询字段
    if isinstance(case_obj, dict):
        for key in ("queries", "search_queries", "query_log"):
            block = case_obj.get(key)
            if isinstance(block, dict):
                for db, q in sorted(block.items()):
                    qs = q if isinstance(q, list) else [q]
                    for one in qs:
                        if isinstance(one, str):
                            add(str(db).lower(), one, "case.json", key)

    # (b) task.md：同一行内出现数据库名与带引号检索式 → 关联
    for lineno, line in enumerate(task_text.splitlines(), 1):
        dbs_in_line = [db for db in KNOWN_DBS
                       if re.search(r"(?<![a-z])" + db + r"(?![a-z])",
                                    line, re.IGNORECASE)]
        if not dbs_in_line:
            continue
        for m in QUOTED_RE.finditer(line):
            q = m.group(1) or m.group(2)
            for db in dbs_in_line:
                add(db, q, "task.md", "line %d" % lineno)

    # (c) 材料信封自带的 query 回显
    for fname, classification, env in envelopes:
        if env is None:
            continue
        q = None
        if classification == "crossref":
            msg = env.get("message") or {}
            q = env.get("query") or msg.get("query")
        elif classification == "europepmc":
            req = env.get("request") or {}
            q = env.get("query") or req.get("query")
        if isinstance(q, str) and classification in KNOWN_DBS:
            add(classification, q, fname, "envelope.query")

    return evidence


# ---------------------------------------------------------------------------
# 台账与报告渲染
# ---------------------------------------------------------------------------

def make_entry(entries, etype, db, evidence, **fmt):
    spec = ENTRY_SPECS[etype]
    fmt.setdefault("db", db)
    entries.append({
        "type": etype,
        "severity": spec["severity"],
        "db": db,
        "evidence": evidence,
        "impact": spec["impact"].format(**fmt),
    })


def render_matrix_md(matrix, systematic_gaps):
    dbs = matrix["dbs"]
    fields = matrix["fields"]
    cells = matrix["cells"]
    lines = []
    lines.append("# 字段覆盖矩阵（Field Coverage Matrix）")
    lines.append("")
    lines.append("单元格 = 该数据库实际提供该字段的记录条数；"
                 "0 且该库有记录 = 系统性缺口（systematic_gap）。")
    lines.append("")
    header = "| 字段 | " + " | ".join(dbs) + " |"
    lines.append(header)
    lines.append("|" + "---|" * (len(dbs) + 1))
    for field in fields:
        row = [field] + [str(cells.get(db, {}).get(field, 0)) for db in dbs]
        lines.append("| " + " | ".join(row) + " |")
    counts = matrix.get("record_counts", {})
    lines.append("| **记录总数** | " + " | ".join(str(counts.get(db, 0))
                                                    for db in dbs) + " |")
    lines.append("")
    if systematic_gaps:
        lines.append("## 系统性字段缺口（0 次提供的 字段×库 组合）")
        lines.append("")
        for gap in systematic_gaps:
            lines.append("- `%s` × `%s`：0 次提供" % (gap["field"], gap["db"]))
        lines.append("")
    return "\n".join(lines) + "\n"


def render_omission_md(case_id, note, entries, sources):
    lines = []
    lines.append("# 遗漏与缺口报告（Omission & Gap Report）")
    lines.append("")
    lines.append("- case_id：`%s`" % case_id)
    if note:
        lines.append("- 备注：%s" % note)
    lines.append("- 期望数据库：%s" % (", ".join(sources["dbs_expected"]) or "（未声明）"))
    lines.append("- 有材料的数据库：%s" % (", ".join(sources["dbs_with_material"]) or "（无）"))
    lines.append("- 缺席数据库：%s" % (", ".join(sources["dbs_absent"]) or "（无）"))
    lines.append("- 台账条目总数：%d" % len(entries))
    lines.append("")
    lines.append("每条目包含：类型、严重级、证据定位、影响陈述"
                 "（「由于该缺口，用户无法得出什么结论」）。任何缺口均未被静默吞没。")
    lines.append("")
    if not entries:
        lines.append("（台账为空：未发现可声明的缺口或异常。）")
        lines.append("")
    for e in entries:
        lines.append("## %s — %s（%s）" % (e["entry_id"], e["type"], e["severity"]))
        lines.append("")
        if e.get("db"):
            lines.append("- 数据库：`%s`" % e["db"])
        ev = e.get("evidence") or {}
        for k in sorted(ev):
            lines.append("- 证据 %s：`%s`" % (k, ev[k]))
        lines.append("- 影响：%s" % e["impact"])
        lines.append("")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def build_skeleton():
    return {
        "case_id": None,
        "status": "partial",
        "sources": {},
        "uncertainty": "审计尚未完成：STEP 0 骨架已写出，输入尚未读取。",
        "gap_counts": {},
        "unresolved_contract_fields": [],
        "change_records": [{
            "action": "step0_skeleton_written",
            "artifact": "result.json",
            "detail": "在读取任何输入之前写出 status=partial 骨架",
        }],
        "generator": {"skill": "coverage-cartographer",
                      "script": "coverage_cartographer.py",
                      "deterministic": True},
    }


def run(args):
    change_records = [{
        "action": "step0_skeleton_written",
        "artifact": "result.json",
        "detail": "在读取任何输入之前写出 status=partial 骨架",
    }]

    os.makedirs(args.work, exist_ok=True)
    os.makedirs(args.out, exist_ok=True)
    result_path = os.path.join(args.out, "result.json")

    # ---- STEP 0：先写骨架 -------------------------------------------------
    write_json(result_path, build_skeleton())

    # ---- 读取 case.json（无效输入 → exit 3） ------------------------------
    if not os.path.isfile(args.case):
        skeleton = build_skeleton()
        skeleton["status"] = "failed"
        skeleton["uncertainty"] = "case.json 不存在：%s" % args.case
        skeleton["change_records"].append({
            "action": "input_invalid", "detail": "case.json missing: %s" % args.case})
        write_json(result_path, skeleton)
        return 3
    try:
        case_obj = json.loads(read_text(args.case))
        if not isinstance(case_obj, dict):
            raise ValueError("case.json top-level is not an object")
    except (ValueError, OSError) as exc:
        skeleton = build_skeleton()
        skeleton["status"] = "failed"
        skeleton["uncertainty"] = "case.json 不可解析：%s" % exc
        skeleton["change_records"].append({
            "action": "input_invalid", "detail": "case.json unparseable: %s" % exc})
        write_json(result_path, skeleton)
        return 3

    case_id = case_obj.get("case_id")
    case_note = case_obj.get("_note")
    task_text = ""
    task_found = os.path.isfile(args.task)
    if task_found:
        task_text = read_text(args.task)
    change_records.append({
        "action": "inputs_loaded",
        "case": os.path.abspath(args.case),
        "task": os.path.abspath(args.task),
        "task_found": task_found,
    })

    ledger = []

    # ---- 1. 材料发现 + 嗅探分类 -------------------------------------------
    case_dir = os.path.dirname(os.path.abspath(args.case))
    listed = case_obj.get("materials") or []
    if isinstance(listed, str):
        listed = [listed]
    material_paths, listed_abs = [], set()
    for m in listed:
        p = m if os.path.isabs(str(m)) else os.path.join(case_dir, str(m))
        p = os.path.abspath(p)
        listed_abs.add(p)
        material_paths.append((p, True))
    for fname in sorted(os.listdir(case_dir)):
        if not fname.lower().endswith((".json", ".jsonl")):
            continue
        p = os.path.join(case_dir, fname)
        if p == os.path.abspath(args.case) or p in listed_abs:
            continue
        material_paths.append((p, False))
    # 去重并保持确定顺序
    seen_paths, ordered = set(), []
    for p, was_listed in material_paths:
        if p not in seen_paths:
            seen_paths.add(p)
            ordered.append((p, was_listed))
    material_paths = ordered

    classified = []   # {"file","classification","db","record_count","envelope","records"}
    all_records = []  # 规范化文献记录
    envelopes = []    # (file, classification, envelope) 供查询证据/分页审计
    reference_graphs = []
    import_states = []

    for path, was_listed in material_paths:
        fname = os.path.basename(path)
        if not os.path.isfile(path):
            make_entry(ledger, "material_missing", None,
                       {"file": fname, "locator": "case.json materials"},
                       file=fname)
            continue
        try:
            text = read_text(path)
        except OSError as exc:
            make_entry(ledger, "envelope_malformed", None,
                       {"file": fname, "locator": "read error: %s" % exc},
                       file=fname)
            continue
        classification, db, records, envelope, note = classify_material(path, text)
        item = {"file": fname, "classification": classification, "db": db,
                "record_count": len(records),
                "listed_in_case": was_listed, "note": note}
        classified.append(item)
        all_records.extend(records)
        envelopes.append((fname, classification, envelope))
        if classification == "reference_graph":
            reference_graphs.append((fname, envelope))
        elif classification == "import_state":
            import_states.append((fname, envelope))
        elif classification == "malformed":
            make_entry(ledger, "envelope_malformed", None,
                       {"file": fname, "locator": "json/jsonl parse failed"},
                       file=fname)
        elif classification == "unknown":
            make_entry(ledger, "unclassified_material", None,
                       {"file": fname, "locator": note or "unknown shape"},
                       file=fname)
        elif classification in KNOWN_DBS and not records:
            make_entry(ledger, "empty_response", db,
                       {"file": fname, "locator": "0 records in envelope"})
    change_records.append({
        "action": "materials_classified",
        "count": len(classified),
        "files": [{k: c[k] for k in ("file", "classification", "db", "record_count")}
                  for c in classified],
    })

    # ---- 2. 数据库盘点 vs 期望集合 ----------------------------------------
    expected = set()
    src_dbs = case_obj.get("source_dbs") or []
    if isinstance(src_dbs, str):
        src_dbs = [src_dbs]
    for d in src_dbs:
        expected.add(str(d).strip().lower())
    for db in KNOWN_DBS:
        if re.search(r"(?<![a-z])" + db + r"(?![a-z])", task_text, re.IGNORECASE):
            expected.add(db)
    expected = sorted(expected)

    dbs_with_material = sorted({c["db"] for c in classified
                                if c["db"] in KNOWN_DBS})
    dbs_absent = [d for d in expected if d not in dbs_with_material]
    extra_sources = [d for d in dbs_with_material if d not in expected]
    for d in dbs_absent:
        make_entry(ledger, "db_absent", d,
                   {"locator": "case.json source_dbs / task.md", "db": d})
    for d in extra_sources:
        make_entry(ledger, "extra_source", d,
                   {"locator": "classified materials", "db": d})

    # ---- 3. 检索编排审计 ---------------------------------------------------
    query_evidence = extract_query_evidence(case_obj, task_text, envelopes)
    by_query = {}
    for ev in query_evidence:
        by_query.setdefault(ev["query"], set()).add(ev["db"])
    for q in sorted(by_query):
        dbs = sorted(by_query[q])
        if len(dbs) < 2:
            continue
        differs = any(DB_SYNTAX_DIFFERS.get(tuple(sorted((a, b))), True)
                      for i, a in enumerate(dbs) for b in dbs[i + 1:])
        if differs:
            make_entry(ledger, "mechanical_copy", ",".join(dbs),
                       {"query": q, "dbs": ",".join(dbs),
                        "locator": "task.md / case.json query evidence"},
                       dbs="、".join(dbs))
    evidenced_dbs = {ev["db"] for ev in query_evidence}
    for c in classified:
        if c["db"] in KNOWN_DBS and c["record_count"] > 0 \
                and c["db"] not in evidenced_dbs:
            make_entry(ledger, "query_evidence_missing", c["db"],
                       {"db": c["db"], "locator": "no query string found in "
                        "case.json / task.md / envelope"})

    # 分页 / 命中数审计
    for c in classified:
        if c["classification"] == "crossref":
            env = next((e for f, cl, e in envelopes
                        if f == c["file"] and cl == "crossref"), None)
            msg = (env or {}).get("message") or {}
            total = msg.get("total-results")
            returned = c["record_count"]
            cursor_evidence = any(k in msg for k in
                                  ("cursor", "next-cursor", "next_cursor"))
            if isinstance(total, int) and total != returned and not cursor_evidence:
                make_entry(ledger, "hitcount_mismatch", "crossref",
                           {"file": c["file"],
                            "locator": "message.total-results=%s vs items=%d"
                                       % (total, returned)},
                           declared=total, returned=returned)
        elif c["classification"] == "europepmc":
            env = next((e for f, cl, e in envelopes
                        if f == c["file"] and cl == "europepmc"), None)
            env = env or {}
            total = env.get("hitCount")
            returned = c["record_count"]
            page_evidence = any(k in env for k in
                                ("cursorMark", "nextPageUrl", "page"))
            try:
                total_int = int(total)
            except (TypeError, ValueError):
                total_int = None
            if total_int is not None and total_int != returned and not page_evidence:
                make_entry(ledger, "hitcount_mismatch", "europepmc",
                           {"file": c["file"],
                            "locator": "hitCount=%s vs result=%d"
                                       % (total_int, returned)},
                           declared=total_int, returned=returned)

    # ---- 4. 字段覆盖矩阵 ----------------------------------------------------
    matrix_dbs = sorted({c["db"] for c in classified if c["db"] in KNOWN_DBS})
    cells = {db: {f: 0 for f in CANONICAL_FIELDS} for db in matrix_dbs}
    record_counts = {db: 0 for db in matrix_dbs}
    for rec in all_records:
        db = rec["source_db"]
        if db not in cells:
            continue
        record_counts[db] += 1
        for f in rec["provided_fields"]:
            cells[db][f] += 1
    systematic_gaps = []
    for db in matrix_dbs:
        if record_counts[db] == 0:
            continue
        for f in CANONICAL_FIELDS:
            if cells[db][f] == 0:
                systematic_gaps.append({"db": db, "field": f})
                make_entry(ledger, "field_systematic_gap", db,
                           {"db": db, "field": f,
                            "locator": "coverage_matrix cells[%s][%s]=0 over %d records"
                                       % (db, f, record_counts[db])},
                           field=f, count=record_counts[db])
    matrix = {"fields": CANONICAL_FIELDS, "dbs": matrix_dbs,
              "cells": cells, "record_counts": record_counts}

    # ---- 跨源身份归并（并查集：doi / pmid / 复合键） ------------------------
    n = len(all_records)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    key_owner = {}
    for i, rec in enumerate(all_records):
        keys = []
        if rec.get("doi"):
            keys.append("doi:" + rec["doi"])
        if rec.get("pmid"):
            keys.append("pmid:" + str(rec["pmid"]))
        ck = comp_key(rec)
        if ck:
            keys.append("comp:" + ck)
        for k in keys:
            if k in key_owner:
                union(i, key_owner[k])
            else:
                key_owner[k] = i
    groups = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    canonical = []
    for members in groups.values():
        recs = [all_records[i] for i in sorted(members)]
        doi = next((r["doi"] for r in recs if r.get("doi")), None)
        pmid = next((str(r["pmid"]) for r in recs if r.get("pmid")), None)
        title = next((r["title"] for r in recs if r.get("title")), None)
        year = next((r["year"] for r in recs if r.get("year")), None)
        dbs = sorted({r["source_db"] for r in recs})
        fields_avail = sorted({f for r in recs for f in r["provided_fields"]})
        identity = ("doi:" + doi) if doi else (
            ("pmid:" + pmid) if pmid else "comp:" + (comp_key(recs[0]) or "?"))
        canonical.append({
            "identity_key": identity,
            "doi": doi,
            "pmid": pmid,
            "title": title,
            "year": year,
            "dbs": dbs,
            "source_files": sorted({r["source_file"] for r in recs}),
            "fields_available": fields_avail,
            "fields_missing": [f for f in CANONICAL_FIELDS
                               if f not in fields_avail],
        })
    canonical.sort(key=lambda c: c["identity_key"])

    # 单一来源文献
    single_source_only = []
    for c in canonical:
        if len(c["dbs"]) == 1:
            single_source_only.append({
                "identity_key": c["identity_key"],
                "title": c["title"],
                "db": c["dbs"][0],
            })
            make_entry(ledger, "single_source_only", c["dbs"][0],
                       {"identity": c["identity_key"],
                        "locator": ",".join(c["source_files"])},
                       identity=c["identity_key"])

    # ---- 5. 标识符冲突（列待仲裁，不静默解决） ------------------------------
    by_doi = {}
    for rec in all_records:
        if rec.get("doi"):
            by_doi.setdefault(rec["doi"], []).append(rec)
    for doi in sorted(by_doi):
        recs = by_doi[doi]
        dbs = sorted({r["source_db"] for r in recs})
        if len(dbs) < 2:
            continue
        years, titles = {}, {}
        for r in recs:
            if r.get("year"):
                years.setdefault(r["source_db"], set()).add(r["year"])
            if r.get("title"):
                titles.setdefault(r["source_db"], set()).add(
                    norm_title(r["title"]) or "")
        distinct_years = sorted({y for s in years.values() for y in s})
        distinct_titles = sorted({t for s in titles.values() for t in s})
        if len(distinct_years) > 1 or len(distinct_titles) > 1:
            detail_parts = []
            if len(distinct_years) > 1:
                detail_parts.append("year: " + "; ".join(
                    "%s=%s" % (d, "/".join(sorted(years[d])))
                    for d in sorted(years)))
            if len(distinct_titles) > 1:
                detail_parts.append("title 归一化后仍不一致（%d 种）"
                                    % len(distinct_titles))
            make_entry(ledger, "identifier_conflict", ",".join(dbs),
                       {"identifier": "doi:" + doi,
                        "locator": ",".join(sorted({r["source_file"]
                                                    for r in recs}))},
                       identifier="doi:" + doi, detail="；".join(detail_parts))

    # ---- 6. 增量导入状态对账 -------------------------------------------------
    retrieved_ids = {"doi": set(), "pmid": set(), "pmcid": set()}
    for rec in all_records:
        if rec.get("doi"):
            retrieved_ids["doi"].add(rec["doi"])
        if rec.get("pmid"):
            retrieved_ids["pmid"].add(str(rec["pmid"]))
        if rec.get("pmcid"):
            retrieved_ids["pmcid"].add(str(rec["pmcid"]).lower())

    def parse_imported(raw):
        s = str(raw).strip()
        low = s.lower()
        if low.startswith("doi:"):
            return "doi", norm_doi(s[4:])
        if low.startswith("pmid:"):
            return "pmid", s[5:].strip()
        if low.startswith("pmcid:"):
            return "pmcid", s[6:].strip().lower()
        if "/" in s:
            return "doi", norm_doi(s)
        if low.startswith("pmc"):
            return "pmcid", low
        return ("pmid", s) if s.isdigit() else ("unknown", s)

    for fname, state in import_states:
        claimed = {"doi": set(), "pmid": set(), "pmcid": set(), "unknown": set()}
        for raw in state.get("imported_ids") or []:
            kind, value = parse_imported(raw)
            if value:
                claimed[kind].add(value)
        for kind in ("doi", "pmid", "pmcid"):
            for value in sorted(claimed[kind] - retrieved_ids[kind]):
                make_entry(ledger, "import_state_gap", state.get("db"),
                           {"file": fname, "identifier": "%s:%s" % (kind, value),
                            "locator": "imported_ids 中声明但检索响应中不存在"},
                           direction="claimed_not_in_responses",
                           identifier="%s:%s" % (kind, value))
            for value in sorted(retrieved_ids[kind] - claimed[kind]):
                make_entry(ledger, "import_state_gap", state.get("db"),
                           {"file": fname, "identifier": "%s:%s" % (kind, value),
                            "locator": "检索响应中存在但 imported_ids 未声明"},
                           direction="in_responses_not_imported",
                           identifier="%s:%s" % (kind, value))

    # ---- 7. 引用图断点 -------------------------------------------------------
    retrieved_dois = retrieved_ids["doi"]
    retrieved_comps = {comp_key(r) for r in all_records if comp_key(r)}
    for fname, graph in reference_graphs:
        for node in graph.get("nodes") or []:
            if not isinstance(node, dict):
                continue
            ndoi = norm_doi(node.get("doi"))
            ncomp = comp_key({"title": node.get("title"),
                              "year": node.get("year"),
                              "first_author_family": node.get("first_author_family")})
            matched = (ndoi and ndoi in retrieved_dois) or \
                      (ncomp and ncomp in retrieved_comps)
            if not matched:
                label = node.get("id") or ndoi or node.get("title") or "?"
                make_entry(ledger, "referenced_not_retrieved", None,
                           {"file": fname, "node": str(label),
                            "locator": "reference_graph.nodes "
                                       "(doi=%s)" % (ndoi or "none")},
                           node=str(label))

    # ---- 台账定序与编号（确定性） -------------------------------------------
    ledger.sort(key=lambda e: (e["type"], e.get("db") or "",
                               json.dumps(e["evidence"], sort_keys=True)))
    for i, e in enumerate(ledger, 1):
        e["entry_id"] = "gap-%04d" % i

    # ---- 产出物 --------------------------------------------------------------
    sources = {
        "materials": classified,
        "dbs_expected": expected,
        "dbs_with_material": dbs_with_material,
        "dbs_absent": dbs_absent,
        "extra_sources": extra_sources,
    }
    coverage_summary = {
        "dbs_expected": expected,
        "dbs_with_material": dbs_with_material,
        "dbs_absent": dbs_absent,
        "extra_sources": extra_sources,
        "record_counts": record_counts,
        "canonical_paper_count": len(canonical),
        "single_source_only": single_source_only,
        "field_coverage": matrix,
        "systematic_gaps": systematic_gaps,
        "query_evidence": query_evidence,
    }
    by_type, by_severity = {}, {}
    for e in ledger:
        by_type[e["type"]] = by_type.get(e["type"], 0) + 1
        by_severity[e["severity"]] = by_severity.get(e["severity"], 0) + 1
    gap_counts = {"total": len(ledger), "by_type": by_type,
                  "by_severity": by_severity}

    if ledger:
        uncertainty = (
            "本次审计共登记 %d 条缺口/异常（%s）。在相应缺口关闭之前，"
            "候选集的完备性不能断言；所有结论均以 gap_ledger.json 与 "
            "omission_report.md 中的证据定位为准。缺失证据一律如实声明，"
            "未做任何静默假设。" % (
                len(ledger),
                "；".join("%s×%d" % (t, by_type[t]) for t in sorted(by_type))))
        status = "partial"
    else:
        uncertainty = ("台账为空：在已发现材料的范围内未发现可声明的缺口；"
                       "该结论仅覆盖已提供的材料本身。")
        status = "ok"

    change_records.append({
        "action": "audit_completed",
        "canonical_papers": len(canonical),
        "ledger_entries": len(ledger),
        "systematic_gaps": len(systematic_gaps),
    })

    # ---- 输出契约填充 ---------------------------------------------------------
    contract = case_obj.get("output_contract") or {}
    if not isinstance(contract, dict):
        contract = {}
    fillers = {
        "candidate_set": canonical,
        "coverage_summary": coverage_summary,
        "gap_summary": ledger,
        "uncertainty_statement": uncertainty,
        "change_records": change_records,
        "status": status,
        "sources": sources,
        "uncertainty": uncertainty,
    }

    def shape_of(decl):
        s = str(decl).lower()
        if any(k in s for k in ("list", "array")):
            return "list"
        if any(k in s for k in ("dict", "object", "map")):
            return "dict"
        if "str" in s or "text" in s:
            return "string"
        return None

    result = {
        "case_id": case_id,
        "status": status,
        "sources": sources,
        "uncertainty": uncertainty,
        "gap_counts": gap_counts,
        "unresolved_contract_fields": [],
        "change_records": change_records,
        "generator": {"skill": "coverage-cartographer",
                      "script": "coverage_cartographer.py",
                      "deterministic": True},
    }
    if case_note:
        result["note"] = case_note

    unresolved = []
    for field in sorted(contract):
        declared = contract[field]
        want = shape_of(declared)
        if field in fillers:
            value = fillers[field]
            if want == "list" and not isinstance(value, list):
                value = list(value) if value is not None else []
            elif want == "dict" and not isinstance(value, dict):
                value = {"value": value}
            elif want == "string" and not isinstance(value, str):
                value = json.dumps(value, ensure_ascii=False, sort_keys=True)
            result[field] = value
        else:
            # 无法填充：null + 登记，绝不编造
            result[field] = None
            unresolved.append(field)
    result["unresolved_contract_fields"] = unresolved

    # ---- 写盘 -----------------------------------------------------------------
    write_json(os.path.join(args.out, "gap_ledger.json"),
               {"case_id": case_id, "summary": gap_counts, "entries": ledger})
    write_json(os.path.join(args.out, "coverage_matrix.json"), matrix)
    write_text(os.path.join(args.out, "coverage_matrix.md"),
               render_matrix_md(matrix, systematic_gaps))
    write_text(os.path.join(args.out, "omission_report.md"),
               render_omission_md(case_id, case_note, ledger, sources))
    write_json(os.path.join(args.work, "normalized_records.json"),
               {"records": all_records})
    write_json(result_path, result)
    change_records.append({
        "action": "artifacts_written",
        "artifacts": ["result.json", "gap_ledger.json", "coverage_matrix.json",
                      "coverage_matrix.md", "omission_report.md"],
        "work_artifacts": ["normalized_records.json"],
    })
    # change_records 追记后重写一次 result.json，保持自洽
    write_json(result_path, result)

    print("coverage-cartographer: case=%s status=%s ledger=%d canonical=%d" % (
        case_id, result["status"], len(ledger), len(canonical)))
    return 2 if unresolved else 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="coverage_cartographer.py",
        description="覆盖制图师：多数据库联合检索的覆盖完备性审计与缺口诚实化。"
                    "离线、确定性、仅标准库。")
    parser.add_argument("--case", default="/input/case.json",
                        help="案例 JSON 路径（默认 /input/case.json）")
    parser.add_argument("--task", default="/input/task.md",
                        help="任务说明 Markdown 路径（默认 /input/task.md）")
    parser.add_argument("--work", default="/app/work",
                        help="中间产物目录（默认 /app/work）")
    parser.add_argument("--out", default="/app/output",
                        help="交付物目录（默认 /app/output）")
    args = parser.parse_args(argv)
    try:
        return run(args)
    except SystemExit:
        raise
    except Exception as exc:  # 顶层兜底：诚实 partial + exit 2，绝不崩溃
        traceback.print_exc()
        try:
            os.makedirs(args.out, exist_ok=True)
            skeleton = build_skeleton()
            skeleton["status"] = "partial"
            skeleton["uncertainty"] = (
                "脚本级异常导致审计未完成：%s: %s。已写出诚实降级骨架。"
                % (type(exc).__name__, exc))
            skeleton["change_records"].append({
                "action": "top_level_exception",
                "detail": "%s: %s" % (type(exc).__name__, exc)})
            write_json(os.path.join(args.out, "result.json"), skeleton)
        except Exception:
            pass
        return 2


if __name__ == "__main__":
    sys.exit(main())
