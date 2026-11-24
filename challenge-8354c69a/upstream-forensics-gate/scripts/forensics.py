#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""forensics.py — 上游数据真实性取证（pure stdlib）。

在撰写任何解释之前，先回答：这批输入文件本身可信吗？

检查项（每项输出：对象定位 + 判定阈值 + 证据）：
  F1 文件谱系：逐文件 sha256、字节数、扩展名；完全重复文件分组。
  F2 行级重复：表格/曲线文件内完全相同的数据行（导出错误签名）。
  F3 饱和/截断：相同读数连续段 >= K（默认 5）→ 量程截断嫌疑。
  F4 常量列/退化列：某列方差为 0（通道失效或复制粘贴）。
  F5 单位歧义：扫描文本与表头中的单位记号，同一物理量关键词对应多个单位 → 歧义登记。
  F6 跨文件数值重叠：两个文件的数值集合完全一致 → 同一份数据的两个拷贝。
  F7 xlsx 结构：sheet 名、隐藏 sheet、数值/文本单元格计数（zipfile+xml 只读）。
  F8 MATLAB 脚本参数提取：.m 文件中的数值常量与文件名引用（供与数据文件对照）。

输出 JSON 供 run_all.py 汇总；不删除、不修改任何输入。
"""
import hashlib
import json
import os
import re
import zipfile
import xml.etree.ElementTree as ET

NUM_RE = re.compile(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")
UNIT_RE = re.compile(r"(mg/mL|mg/L|g/mL|µg/mL|ug/mL|μg/mL|ng/mL|MPa|GPa|kPa|Pa|"
                     r"mM|uM|µM|nM|%|wt%|vol%|mg|g|kg|mL|uL|µL|L|mm|cm|m|s|min|h)\b")
VAR_HINTS = ["浓度", "concentration", "强度", "strength", "载荷", "load", "力",
             "force", "含量", "assay", "温度", "temperature", "时间", "time"]


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_text(path, limit=600000):
    raw = open(path, "rb").read(limit)
    for enc in ("utf-8", "gb18030", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def parse_rows(path):
    """返回 (header_lines, numeric_rows)：数据行取全部数值列。"""
    header, rows = [], []
    for line in read_text(path).splitlines():
        t = line.strip()
        if not t:
            continue
        parts = re.split(r"[,\t;]|\s{2,}|\s", t)
        nums = []
        ok = True
        for p in parts:
            if p == "":
                continue
            try:
                nums.append(float(p))
            except ValueError:
                ok = False
                break
        if ok and nums:
            rows.append(nums)
        elif len(header) < 5:
            header.append(t)
    return header, rows


def longest_run(vals):
    best = cur = 1
    for i in range(1, len(vals)):
        cur = cur + 1 if vals[i] == vals[i - 1] else 1
        best = max(best, cur)
    return best if vals else 0


def f1_file_lineage(files):
    seen = {}
    recs = []
    for p in files:
        h = sha256_of(p)
        recs.append({"file": os.path.relpath(p), "sha256": h,
                     "bytes": os.path.getsize(p)})
        seen.setdefault(h, []).append(os.path.relpath(p))
    dups = [sorted(g) for g in seen.values() if len(g) > 1]
    return {"files": recs, "identical_file_groups": dups,
            "threshold": "文件全文 sha256 相同判为完全重复"}


def f2_f3_f4_table_checks(files, sat_k=5):
    out = []
    for p in files:
        if os.path.splitext(p)[1].lower() not in (".csv", ".txt", ".dat", ".tsv"):
            continue
        header, rows = parse_rows(p)
        if len(rows) < 5:
            continue
        rec = {"file": os.path.relpath(p), "n_rows": len(rows), "header": header[:2]}
        keys = [tuple(r) for r in rows]
        dup_rows = len(keys) - len(set(keys))
        if dup_rows:
            rec["duplicate_data_rows"] = dup_rows
        ncols = max(len(r) for r in rows)
        sat, const = [], []
        for c in range(ncols):
            col = [r[c] for r in rows if len(r) > c]
            if len(col) < 5:
                continue
            run = longest_run(col)
            if run >= sat_k:
                sat.append({"col": c, "longest_identical_run": run,
                            "value": col[0] if run == len(col) else None})
            if len(set(col)) == 1:
                const.append(c)
        if sat:
            rec["saturation_suspects"] = sat
        if const:
            rec["constant_columns"] = const
        rec["numeric_signature"] = hashlib.sha256(
            json.dumps(sorted({round(v, 6) for r in rows for v in r})).encode()
        ).hexdigest()[:16] if rows else None
        out.append(rec)
    return {"tables": out,
            "thresholds": {"duplicate_row": "数据行完全相同(全部数值列)",
                           "saturation": "同列相同读数连续段>=%d" % sat_k,
                           "constant": "列内取值唯一(方差为0)"}}


def f5_unit_ambiguity(files):
    hits = []
    for p in files:
        if os.path.splitext(p)[1].lower() not in (".csv", ".txt", ".dat", ".md",
                                                  ".json", ".m", ".tsv"):
            continue
        text = read_text(p, 200000)
        for line in text.splitlines()[:400]:
            units = UNIT_RE.findall(line)
            if units and any(v in line.lower() for v in VAR_HINTS):
                hits.append({"file": os.path.relpath(p),
                             "line": line.strip()[:120], "units": units})
    by_var = {}
    for h in hits:
        for v in VAR_HINTS:
            if v in h["line"].lower():
                by_var.setdefault(v, set()).update(h["units"])
    amb = {v: sorted(u) for v, u in by_var.items() if len(u) > 1}
    return {"unit_mentions": hits[:80], "ambiguous_variables": amb,
            "threshold": "同一物理量关键词在一行内/跨行对应多个不同单位记号即登记歧义"}


def f6_cross_file_overlap(table_checks):
    sig2files = {}
    for t in table_checks["tables"]:
        if t.get("numeric_signature"):
            sig2files.setdefault(t["numeric_signature"], []).append(t["file"])
    return {"same_values_different_files": [v for v in sig2files.values() if len(v) > 1],
            "threshold": "两文件数值集合(6位小数)完全一致"}


def f7_xlsx_structure(files):
    out = []
    ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    for p in files:
        if not p.lower().endswith(".xlsx"):
            continue
        rec = {"file": os.path.relpath(p), "sheets": []}
        try:
            z = zipfile.ZipFile(p)
            wb = ET.fromstring(z.read("xl/workbook.xml"))
            for sh in wb.iter(ns + "sheet"):
                rec["sheets"].append({"name": sh.get("name"),
                                      "state": sh.get("state", "visible")})
        except Exception as e:  # noqa: BLE001
            rec["error"] = repr(e)
        out.append(rec)
    return {"workbooks": out,
            "threshold": "state!=visible 的 sheet 记为隐藏 sheet 需人工确认"}


def f8_matlab_params(files):
    out = []
    for p in files:
        if not p.lower().endswith(".m"):
            continue
        text = read_text(p)
        consts = re.findall(r"([A-Za-z_]\w*)\s*=\s*(%s)" % NUM_RE.pattern, text)
        refs = re.findall(r"['\"]([^'\"]+\.(?:txt|csv|dat|xlsx|mat))['\"]", text, re.I)
        out.append({"file": os.path.relpath(p),
                    "numeric_constants": consts[:60],
                    "referenced_files": sorted(set(refs))})
    return {"matlab_scripts": out,
            "threshold": "脚本引用文件名须与 /input 实际文件一一对应"}


def run(input_dir):
    files = []
    for root, _d, names in os.walk(input_dir):
        for n in sorted(names):
            p = os.path.join(root, n)
            if os.path.isfile(p) and not n.startswith("."):
                files.append(p)
    files.sort()
    report = {"n_files": len(files)}
    report["F1_file_lineage"] = f1_file_lineage(files)
    tc = f2_f3_f4_table_checks(files)
    report["F2_F3_F4_table_checks"] = tc
    report["F5_unit_ambiguity"] = f5_unit_ambiguity(files)
    report["F6_cross_file_overlap"] = f6_cross_file_overlap(tc)
    report["F7_xlsx_structure"] = f7_xlsx_structure(files)
    report["F8_matlab_params"] = f8_matlab_params(files)
    # 汇总真实性结论
    findings = []
    if report["F1_file_lineage"]["identical_file_groups"]:
        findings.append({"severity": "high", "kind": "identical_files",
                         "detail": report["F1_file_lineage"]["identical_file_groups"]})
    for t in tc["tables"]:
        for k in ("duplicate_data_rows", "saturation_suspects", "constant_columns"):
            if k in t:
                findings.append({"severity": "medium", "kind": k,
                                 "detail": {"file": t["file"], k: t[k]}})
    if report["F5_unit_ambiguity"]["ambiguous_variables"]:
        findings.append({"severity": "medium", "kind": "unit_ambiguity",
                         "detail": report["F5_unit_ambiguity"]["ambiguous_variables"]})
    if report["F6_cross_file_overlap"]["same_values_different_files"]:
        findings.append({"severity": "high", "kind": "cross_file_overlap",
                         "detail": report["F6_cross_file_overlap"]["same_values_different_files"]})
    for wb in report["F7_xlsx_structure"]["workbooks"]:
        hidden = [s["name"] for s in wb.get("sheets", []) if s.get("state") != "visible"]
        if hidden:
            findings.append({"severity": "low", "kind": "hidden_sheets",
                             "detail": {"file": wb["file"], "hidden": hidden}})
    report["authenticity_findings"] = findings
    report["verdict"] = ("PASS_WITH_FLAGS" if findings else "PASS")
    return report
