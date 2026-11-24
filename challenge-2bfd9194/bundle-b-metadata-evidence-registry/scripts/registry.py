#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""registry.py — 元数据字段级证据链引擎（仅标准库）。

核心主张：元数据没有 provenance 就等于没有元数据。
每个字段值必须带可回查出处，按四级来源优先级裁定：

  L1 伴随表格 / 行政备注  -> 定位到 文件#L行号 或 文件#record:键
  L2 文件内容首部 4KB 模式匹配 -> 定位到 文件#L行号
  L3 文件名语法（可配置正则集，每个 pattern 有 id）
  L4 人工/模型裁定（work/metadata_overrides.json，必须给理由字符串）

冲突矩阵：同文件同字段多来源不同值时全部候选保留并标注，winner 按规则：
  1) 存在 L4 裁定时 L4 优先（它是带理由的人工裁决）；
  2) 否则级别低数字优先 L1 > L2 > L3；
  3) 同级按子来源次序：随行 sidecar 行 > 全局行政备注；内容行号小者优先；
     文件名 pattern 按定义次序。

输出（由 run_case.py extract 阶段调用本模块后落盘）：
  metadata_registry.jsonl / conflicts.json / coverage_report.json

也可独立运行：
  python3 scripts/registry.py --scan work/scan_index.json \
      --input /input --work /app/work --out /app/output
"""
import csv
import io
import json
import os
import re
import sys
import unicodedata

# ---------------------------------------------------------------- 字段字典
# 缺省字段集合；可被 case.json 的 metadata_fields / output_contract 扩展（防御式合并）。
FIELD_ALIASES = {
    "project":      ["project", "project_id", "project_code", "grant", "grant_no",
                     "项目", "项目号", "课题", "课题号", "项目编号"],
    "year":         ["year", "年份", "年度"],
    "data_type":    ["data_type", "datatype", "type", "数据类型", "类型"],
    "author":       ["author", "authors", "owner", "作者", "负责人"],
    "instrument":   ["instrument", "device", "仪器", "仪器型号", "设备"],
    "version_note": ["version_note", "version", "版本备注", "版本说明"],
    "retention":    ["retention", "retention_period", "保存期限", "保存期"],
    "access_scope": ["access_scope", "access", "访问权限", "权限范围", "权限"],
    "source_party": ["source_party", "source", "来源", "来源单位", "提供方"],
}
DEFAULT_FIELDS = list(FIELD_ALIASES.keys())

# 全局行政备注只接受这些“安全”字段（项目/年份这类强文件属性不接受全局默认）。
GLOBAL_NOTE_FIELDS = {"instrument", "retention", "access_scope", "source_party", "author"}

# 伴随表中的“文件列”候选名。
FILE_COL_ALIASES = {"file", "filename", "filepath", "path", "文件", "文件名", "文件路径"}

# ---------------------------------------------------------------- L3 文件名正则集（可配置，每个 pattern 有 id）
NAME_PATTERNS = [
    {"id": "rx_year_prefix",   "field": "year",
     "regex": r"^((?:19|20)\d{2})[_\-]"},
    {"id": "rx_year_anywhere", "field": "year",
     "regex": r"(?<!\d)((?:19|20)\d{2})(?!\d)"},
    {"id": "rx_project_code",  "field": "project",
     "regex": r"(?<![A-Za-z0-9])(NSFC[-_]?\d{6,}|[A-Z]{2,5}[-_]\d{3,})(?![A-Za-z0-9])"},
    {"id": "rx_version_suffix", "field": "version_note", "nocase": True,
     "regex": r"(?:^|[_\-（(])(v\d+|final|最终版|终稿|定稿|副本|copy)(?=[)）_.]|$)"},
    {"id": "rx_dtype_raw",     "field": "data_type", "value": "raw_data",
     "nocase": True,
     "regex": r"(?:^|[_\-])raw(?:[_\-.]|$)"},
    {"id": "rx_dtype_report",  "field": "data_type", "value": "report",
     "nocase": True,
     "regex": r"report|报告"},
]

# ---------------------------------------------------------------- L2 内容首部模式集
CONTENT_PATTERNS = [
    {"id": "cx_project_cn",    "field": "project",
     "regex": r"项目号\s*[:：]\s*([^\s，,;；]+)"},
    {"id": "cx_project_en",    "field": "project",
     "regex": r"(?:Project|Grant)(?:\s*No\.?)?\s*[:：]\s*([^\s,;]+)"},
    {"id": "cx_instrument_cn", "field": "instrument",
     "regex": r"仪器(?:型号)?\s*[:：]\s*([^\n\r，,;；]+)"},
    {"id": "cx_instrument_en", "field": "instrument",
     "regex": r"Instrument\s*[:：]\s*([^\n\r,;]+)"},
    {"id": "cx_author_cn",     "field": "author",
     "regex": r"作者\s*[:：]\s*([^\n\r，,;；]+)"},
    {"id": "cx_year_cn",       "field": "year",
     "regex": r"(?:年份|年度)\s*[:：]\s*((?:19|20)\d{2})"},
]

TEXT_EXTS = {".txt", ".md", ".csv", ".tsv", ".json", ".log", ".dat", ".text", ""}
HEAD_BYTES = 4096

CONFIDENCE = {
    ("L1", "sidecar_table"): 0.95,
    ("L1", "sidecar_json"):  0.95,
    ("L1", "admin_note"):    0.80,
    ("L2", "content_head"):  0.85,
    ("L3", "name_pattern"):  0.60,
    ("L4", "manual_override"): 0.99,
}
# 同级子来源次序（数字小者优先）
SUBKIND_ORDER = {"sidecar_table": 0, "sidecar_json": 0, "admin_note": 1,
                 "content_head": 0, "name_pattern": 0, "manual_override": 0}
LEVEL_ORDER = {"L1": 1, "L2": 2, "L3": 3, "L4": 0}  # L4 单独分支处理


def nfc(s):
    return unicodedata.normalize("NFC", s)


def _alias_to_field(fields):
    """alias(小写) -> 规范字段名。"""
    m = {}
    for f in fields:
        m[f.lower()] = f
        for a in FIELD_ALIASES.get(f, []):
            m[a.lower()] = f
    return m


def merge_fields(extra):
    """防御式合并扩展字段。extra 为任意可迭代的名字列表，非法名忽略。"""
    fields = list(DEFAULT_FIELDS)
    if isinstance(extra, (list, tuple)):
        for x in extra:
            if isinstance(x, str) and re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,31}", x) \
                    and x not in fields:
                fields.append(x)
    return fields


def _read_text_head(path, nbytes=HEAD_BYTES):
    """读首部字节并 utf-8/replace 解码；替换符过多视为非文本，返回 None。"""
    try:
        with open(path, "rb") as fh:
            raw = fh.read(nbytes)
    except OSError:
        return None
    text = raw.decode("utf-8", errors="replace")
    if text.count("�") > 16:
        return None
    return text


def _read_lines(path):
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
    except OSError:
        return None
    return raw.decode("utf-8", errors="replace").splitlines()


def _mk(file_rel, field, value, level, kind, locator, pattern_id, note, seq):
    return {
        "file": file_rel, "field": field, "value": str(value).strip(),
        "level": level, "source_kind": kind, "locator": locator,
        "pattern_id": pattern_id,
        "confidence": CONFIDENCE.get((level, kind), 0.5),
        "note": note, "_seq": seq,
    }


# ---------------------------------------------------------------- L1：伴随表格 / 行政备注
def extract_l1(files, input_dir, fields, alias_map):
    """返回 (candidates, sidecar_relpaths)。"""
    cands, sidecars = [], []
    seq = 0
    basenames = {}
    for f in files:
        basenames.setdefault(os.path.basename(f["rel"]), []).append(f["rel"])

    def match_file(token):
        token = nfc(token.strip())
        for f in files:
            if f["rel"] == token:
                return token
        hits = basenames.get(os.path.basename(token), [])
        return hits[0] if len(hits) == 1 else None

    for f in files:
        rel, path = f["rel"], f["path"]
        ext = os.path.splitext(rel)[1].lower()
        if ext in (".csv", ".tsv"):
            lines = _read_lines(path)
            if not lines:
                continue
            delim = "\t" if ext == ".tsv" else ","
            reader = csv.reader(io.StringIO("\n".join(lines)), delimiter=delim)
            try:
                header = next(reader)
            except StopIteration:
                continue
            header_l = [h.strip().lower() for h in header]
            file_col = next((i for i, h in enumerate(header_l) if h in FILE_COL_ALIASES), None)
            if file_col is None:
                continue  # 无文件列 -> 不是伴随元数据表
            col_fields = {}
            for i, h in enumerate(header_l):
                if i != file_col and h in alias_map:
                    col_fields[i] = alias_map[h]
            if not col_fields:
                continue
            sidecars.append(rel)
            for row in reader:
                if len(row) <= file_col:
                    continue
                target = match_file(row[file_col]) if row[file_col].strip() else None
                if not target:
                    continue
                line_no = reader.line_num  # 物理行号（1 起）
                for i, fld in col_fields.items():
                    if i < len(row) and row[i].strip():
                        seq += 1
                        cands.append(_mk(target, fld, row[i], "L1", "sidecar_table",
                                         "%s#L%d" % (rel, line_no), None,
                                         "伴随表列[%s]" % header[i].strip(), seq))
        elif ext == ".json":
            lines = _read_lines(path)
            if not lines:
                continue
            try:
                obj = json.loads("\n".join(lines))
            except ValueError:
                continue
            records = []
            if isinstance(obj, dict):
                records = [{"_key": k, **v} for k, v in obj.items()
                           if isinstance(v, dict)]
            elif isinstance(obj, list):
                records = [r for r in obj if isinstance(r, dict)]
            keyed = False
            for rec in records:
                fkey = rec.get("_key") or next(
                    (rec[k] for k in rec if isinstance(rec[k], str)
                     and k.strip().lower() in FILE_COL_ALIASES), None)
                if not isinstance(fkey, str):
                    continue
                target = match_file(fkey)
                if not target:
                    continue
                keyed = True
                for k, v in rec.items():
                    fld = alias_map.get(str(k).strip().lower())
                    if fld and isinstance(v, (str, int, float)) and str(v).strip():
                        seq += 1
                        cands.append(_mk(target, fld, v, "L1", "sidecar_json",
                                         "%s#record:%s" % (rel, fkey), None,
                                         "伴随JSON键[%s]" % k, seq))
            if keyed:
                sidecars.append(rel)
        elif ext in (".md", ".txt"):
            # 只有文件名带行政/备注/admin 特征的 txt/md 才视为全局行政备注；
            # 普通正文文件里的“作者：”等行只作为该文件自身的 L2 证据。
            if not re.search(r"行政|备注|admin", os.path.basename(rel), re.IGNORECASE):
                continue
            lines = _read_lines(path)
            if not lines:
                continue
            note_hits = []
            for ln, line in enumerate(lines, 1):
                m = re.match(r"^\s*([^\s:：|]{1,20})\s*[:：]\s*(.+?)\s*$", line)
                if not m:
                    continue
                fld = alias_map.get(m.group(1).lower())
                if fld and fld in GLOBAL_NOTE_FIELDS:
                    note_hits.append((fld, m.group(2), ln))
            if note_hits:
                sidecars.append(rel)
                for fld, val, ln in note_hits:
                    seq += 1
                    # 全局备注：先记为 _GLOBAL_ 占位，resolve 阶段按规则下发
                    cands.append(_mk("_GLOBAL_", fld, val, "L1", "admin_note",
                                     "%s#L%d" % (rel, ln), None,
                                     "全局行政备注（仅作用于已有文件级证据的文件）", seq))
    return cands, sorted(set(sidecars))


# ---------------------------------------------------------------- L2：文件内容首部
def extract_l2(files, fields):
    cands, skipped_nontext = [], []
    seq = 100000
    pats = [(p, re.compile(p["regex"])) for p in CONTENT_PATTERNS
            if p["field"] in fields]
    for f in files:
        ext = os.path.splitext(f["rel"])[1].lower()
        if ext not in TEXT_EXTS:
            continue
        head = _read_text_head(f["path"])
        if head is None:
            skipped_nontext.append(f["rel"])
            continue
        lines = head.splitlines()
        hit_fields = set()
        for ln, line in enumerate(lines, 1):
            for p, rx in pats:
                if p["field"] in hit_fields:
                    continue
                m = rx.search(line)
                if m:
                    seq += 1
                    hit_fields.add(p["field"])
                    cands.append(_mk(f["rel"], p["field"], m.group(1), "L2",
                                     "content_head", "%s#L%d" % (f["rel"], ln),
                                     p["id"], "内容首部4KB模式命中", seq))
    return cands, skipped_nontext


# ---------------------------------------------------------------- L3：文件名语法
def extract_l3(files, fields):
    cands = []
    seq = 200000
    for f in files:
        base = os.path.basename(f["rel"])
        for p in NAME_PATTERNS:
            if p["field"] not in fields:
                continue
            seq += 1
            flags = re.IGNORECASE if p.get("nocase") else 0
            m = re.search(p["regex"], base, flags)
            if m:
                value = p.get("value") or (m.group(1) if m.groups() else m.group(0))
                cands.append(_mk(f["rel"], p["field"], value, "L3", "name_pattern",
                                 f["rel"], p["id"], "文件名正则命中", seq))
    return cands


# ---------------------------------------------------------------- L4：人工/模型裁定
def extract_l4(work_dir, fields):
    path = os.path.join(work_dir, "metadata_overrides.json")
    cands = []
    seq = 300000
    if not os.path.isfile(path):
        return cands, None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            obj = json.load(fh)
    except (ValueError, OSError) as e:
        return cands, {"error": "metadata_overrides.json 解析失败: %s" % e}
    if not isinstance(obj, dict):
        return cands, {"error": "metadata_overrides.json 顶层必须是对象"}
    for rel, entry in obj.items():
        if not isinstance(entry, dict):
            continue
        reason = str(entry.get("reason", "")).strip()
        fmap = entry.get("fields", {})
        if not isinstance(fmap, dict):
            continue
        for fld, val in fmap.items():
            if fld not in fields or val in (None, ""):
                continue
            seq += 1
            note = "人工裁定：%s" % (reason or "（未给理由，按规则仍采信但标注）")
            cands.append(_mk(nfc(rel), fld, val, "L4", "manual_override",
                             "metadata_overrides_snapshot.json#%s/%s" % (rel, fld),
                             None, note, seq))
    return cands, obj


# ---------------------------------------------------------------- 裁定与冲突矩阵
def resolve(candidates, files, sidecars, fields, global_note_fields=GLOBAL_NOTE_FIELDS):
    """返回 (registry_winners, conflicts, coverage_seed)。"""
    # 全局行政备注下发：仅作用于已有至少一条文件级证据（非全局备注）的文件
    file_level_evidence = set()
    for c in candidates:
        if c["file"] != "_GLOBAL_" and c["file"] not in sidecars:
            file_level_evidence.add(c["file"])
    expanded = []
    for c in candidates:
        if c["file"] == "_GLOBAL_":
            if c["field"] in global_note_fields:
                for rel in sorted(file_level_evidence):
                    d = dict(c)
                    d["file"] = rel
                    expanded.append(d)
        else:
            expanded.append(c)

    by_key = {}
    for c in expanded:
        by_key.setdefault((c["file"], c["field"]), []).append(c)

    winners, conflicts = [], []
    for (rel, fld), cands in sorted(by_key.items()):
        l4 = [c for c in cands if c["level"] == "L4"]
        if l4:
            winner, rule = sorted(l4, key=lambda c: c["_seq"])[0], "l4_override"
        else:
            ranked = sorted(cands, key=lambda c: (
                LEVEL_ORDER.get(c["level"], 9),
                SUBKIND_ORDER.get(c["source_kind"], 9), c["_seq"]))
            winner, rule = ranked[0], "level_priority"
        w = {k: v for k, v in winner.items() if k != "_seq"}
        if len(cands) > 1:
            w["note"] = (w["note"] + "；共%d条候选" % len(cands)).strip("；")
        winners.append(w)
        distinct = {c["value"] for c in cands}
        if len(distinct) > 1:
            conflicts.append({
                "file": rel, "field": fld,
                "winner": w, "resolution": rule,
                "candidates": [
                    {k: v for k, v in c.items() if k != "_seq"}
                    for c in sorted(cands, key=lambda c: (
                        LEVEL_ORDER.get(c["level"], 9), c["_seq"]))],
                "note": "同文件同字段多来源不同值；全部候选保留，winner 按 %s 裁定" % rule,
            })

    # 覆盖率
    material = [f["rel"] for f in files if f["rel"] not in sidecars]
    filled = {}
    for w in winners:
        filled.setdefault(w["file"], set()).add(w["field"])
    per_field = {}
    for fld in fields:
        n = sum(1 for rel in material if fld in filled.get(rel, set()))
        per_field[fld] = {"filled": n, "total": len(material),
                          "fill_rate": round(n / len(material), 4) if material else None}
    per_level = {}
    for w in winners:
        per_level[w["level"]] = per_level.get(w["level"], 0) + 1
    unfilled = [rel for rel in material if not filled.get(rel)]
    coverage = {
        "fields": fields,
        "denominator_files": len(material),
        "sidecar_files": sorted(sidecars),
        "per_field": per_field,
        "per_level_winner_count": dict(sorted(per_level.items())),
        "unfilled_files": sorted(unfilled),
    }
    return sorted(winners, key=lambda w: (w["file"], w["field"])), conflicts, coverage


def build(scan_index, input_dir, work_dir, extra_fields=None):
    """主入口：scan_index 为 scan 阶段产物 dict。返回结果 dict（不落盘）。"""
    fields = merge_fields(extra_fields)
    alias_map = _alias_to_field(fields)
    files = [{"rel": e["rel"], "path": os.path.join(input_dir, e["rel"])}
             for e in scan_index.get("files", [])]
    files.sort(key=lambda x: x["rel"])

    l1, sidecars = extract_l1(files, input_dir, fields, alias_map)
    sidecar_set = set(sidecars)
    non_sidecar = [f for f in files if f["rel"] not in sidecar_set]
    l2, nontext = extract_l2(non_sidecar, fields)
    l3 = extract_l3(non_sidecar, fields)
    l4, overrides_raw = extract_l4(work_dir, fields)

    winners, conflicts, coverage = resolve(l1 + l2 + l3 + l4, files, sidecar_set, fields)
    coverage["l2_skipped_nontext"] = sorted(nontext)
    return {
        "fields": fields,
        "registry": winners,
        "conflicts": conflicts,
        "coverage": coverage,
        "overrides_raw": overrides_raw,
        "candidate_count": len(l1) + len(l2) + len(l3) + len(l4),
    }


def main(argv):
    import argparse
    ap = argparse.ArgumentParser(description="元数据证据链引擎（独立运行模式）")
    ap.add_argument("--scan", required=True, help="work/scan_index.json")
    ap.add_argument("--input", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--extra-fields", default="")
    args = ap.parse_args(argv)
    with open(args.scan, "r", encoding="utf-8") as fh:
        scan_index = json.load(fh)
    extra = [x for x in args.extra_fields.split(",") if x] or None
    res = build(scan_index, args.input, args.work, extra)
    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "metadata_registry.jsonl"), "w", encoding="utf-8") as fh:
        for w in res["registry"]:
            fh.write(json.dumps(w, ensure_ascii=False) + "\n")
    for name, key in (("conflicts.json", "conflicts"), ("coverage_report.json", "coverage")):
        with open(os.path.join(args.out, name), "w", encoding="utf-8") as fh:
            json.dump(res[key], fh, ensure_ascii=False, indent=2)
    print("registry=%d conflicts=%d" % (len(res["registry"]), len(res["conflicts"])))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
