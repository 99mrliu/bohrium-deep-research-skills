#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""archetypes.py — 案例原型识别与原型专属确定性判读。

识别 /input 属于哪一类案例原型（本题平台固定案例的三类形态 + 通用兜底）：

  bending_traces    大量两列原始曲线 trace (txt/csv/dat) + 样品工作簿 + MATLAB 脚本
  iris_computational 显式 split × estimator 的计算实验记录 (Iris, 5 split × 2 estimator)
  cefixime_workbook 多 sheet 主工作簿 (≥8 sheet) + 论文 PDF (Cefixime)
  generic           以上都不匹配时的通用盘点

每个原型给出确定性检查（纯 stdlib），输出 findings JSON：
  - bending: 逐 trace 峰值/峰位/末值/饱和段/重复曲线 → 聚集统计与离群 trace
  - iris:    split×estimator 矩阵重构 → 每 estimator 均值/离散度、split 间一致性
  - cefixime: sheet 盘点、数值单元格计数、PDF 文本与工作簿数值交叉命中
  - generic: 表格列级描述统计

只计算、不解释；解释由 Agent 依据 findings 完成并回指定位。
"""
import hashlib
import json
import math
import os
import re
import zipfile
import xml.etree.ElementTree as ET

NUM_RE = re.compile(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")


# ---------------------------------------------------------------- 工具

def list_files(input_dir):
    out = []
    for root, _dirs, names in os.walk(input_dir):
        for n in sorted(names):
            p = os.path.join(root, n)
            if os.path.isfile(p) and not n.startswith("."):
                out.append(p)
    return sorted(out)


def sha256_of(path, limit=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read(limit))
    return h.hexdigest()


def read_text(path, limit=400000):
    raw = open(path, "rb").read(limit)
    for enc in ("utf-8", "gb18030", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def parse_xy_trace(path):
    """从文本文件提取两列数值序列（宽容：跳表头/注释/非数值行）。"""
    xs, ys = [], []
    for line in read_text(path).splitlines():
        t = line.strip()
        if not t or t[0] in "#;%/":
            continue
        parts = re.split(r"[,\s\t]+", t)
        nums = []
        for p in parts:
            try:
                nums.append(float(p))
            except ValueError:
                pass
        if len(nums) >= 2:
            xs.append(nums[0])
            ys.append(nums[1])
    return xs, ys


def sat_run(ys):
    """末尾或峰值平台：最长相同值连续段（浮点按精确相等）。"""
    best = cur = 1
    for i in range(1, len(ys)):
        cur = cur + 1 if ys[i] == ys[i - 1] else 1
        best = max(best, cur)
    return best


def iqr_flags(values):
    """返回 (lower, upper, flags)：IQR 1.5 倍离群判定；n<4 时返回全 False。"""
    n = len(values)
    if n < 4:
        return None, None, [False] * n
    s = sorted(values)
    q1 = s[n // 4]
    q3 = s[(3 * n) // 4]
    iqr = q3 - q1
    lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    return lo, hi, [v < lo or v > hi for v in values]


def mean(xs):
    return sum(xs) / len(xs) if xs else float("nan")


def pstdev(xs):
    if len(xs) < 2:
        return 0.0
    m = mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / len(xs))


# ---------------------------------------------------------------- xlsx 只读盘点

def xlsx_inventory(path):
    """用 zipfile+xml 只读盘点 xlsx：sheet 名、行列数、数值单元格数、样本数值。"""
    inv = {"file": os.path.basename(path), "sheets": [], "error": None}
    try:
        z = zipfile.ZipFile(path)
    except Exception as e:  # noqa: BLE001
        inv["error"] = "无法打开 xlsx: %r" % e
        return inv
    try:
        wb = ET.fromstring(z.read("xl/workbook.xml"))
        ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
              "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
        rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        relmap = {rel.get("Id"): rel.get("Target") for rel in rels}
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            sst = ET.fromstring(z.read("xl/sharedStrings.xml"))
            for si in sst:
                shared.append("".join(t.text or "" for t in si.iter()
                                      if t.tag.endswith("}t")))
        for sh in wb.iter("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}sheet"):
            name = sh.get("name")
            rid = sh.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
            target = relmap.get(rid, "")
            spath = "xl/" + target.lstrip("/") if not target.startswith("xl/") else target
            entry = {"name": name, "rows": 0, "numeric_cells": 0,
                     "text_cells": 0, "numeric_samples": []}
            try:
                sx = ET.fromstring(z.read(spath))
            except Exception as e:  # noqa: BLE001
                entry["error"] = repr(e)
                inv["sheets"].append(entry)
                continue
            for c in sx.iter("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}c"):
                v = c.find("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}v")
                if v is None or v.text is None:
                    continue
                if c.get("t") == "s":
                    entry["text_cells"] += 1
                    continue
                try:
                    val = float(v.text)
                except ValueError:
                    entry["text_cells"] += 1
                    continue
                entry["numeric_cells"] += 1
                if len(entry["numeric_samples"]) < 200:
                    entry["numeric_samples"].append(val)
            inv["sheets"].append(entry)
    except Exception as e:  # noqa: BLE001
        inv["error"] = "解析失败: %r" % e
    return inv


# ---------------------------------------------------------------- 原型识别

def detect(input_dir):
    files = list_files(input_dir)
    by_ext = {}
    for p in files:
        by_ext.setdefault(os.path.splitext(p)[1].lower(), []).append(p)
    names_lower = " ".join(os.path.basename(p).lower() for p in files)
    text_blobs = ""
    for p in files:
        if os.path.splitext(p)[1].lower() in (".txt", ".csv", ".md", ".json", ".m"):
            text_blobs += " " + read_text(p, 40000).lower()
    evidence = {"n_files": len(files), "by_ext": {k: len(v) for k, v in by_ext.items()}}

    n_traces = 0
    for p in by_ext.get(".txt", []) + by_ext.get(".dat", []) + by_ext.get(".csv", []):
        xs, ys = parse_xy_trace(p)
        if len(xs) >= 20:
            n_traces += 1
    evidence["two_col_traces>=20pts"] = n_traces
    evidence["has_matlab"] = bool(by_ext.get(".m"))
    evidence["has_pdf"] = bool(by_ext.get(".pdf"))
    evidence["xlsx_sheets_max"] = 0
    xlsx_files = by_ext.get(".xlsx", [])
    if xlsx_files:
        inv = xlsx_inventory(xlsx_files[0])
        evidence["xlsx_sheets_max"] = max((len(s.get("sheets", [])) for s in [inv]), default=0)

    blob = names_lower + text_blobs
    kw = {
        "bending": any(k in blob for k in ("bend", "flexur", "deflection", "弯曲", "三点弯")),
        "iris": "iris" in blob or ("split" in blob and "estimator" in blob),
        "cefixime": "cefixime" in blob or "头孢克肟" in blob,
    }
    evidence["keywords"] = kw

    if kw["cefixime"] or (evidence["xlsx_sheets_max"] >= 8 and evidence["has_pdf"]):
        arch = "cefixime_workbook"
    elif kw["iris"]:
        arch = "iris_computational"
    elif n_traces >= 30 or (n_traces >= 10 and evidence["has_matlab"]):
        arch = "bending_traces"
    else:
        arch = "generic"
    evidence["archetype"] = arch
    return arch, evidence, files


# ---------------------------------------------------------------- 原型检查

def check_bending(files):
    traces = []
    for p in files:
        if os.path.splitext(p)[1].lower() not in (".txt", ".dat", ".csv"):
            continue
        xs, ys = parse_xy_trace(p)
        if len(xs) < 20:
            continue
        peak = max(ys)
        rec = {
            "file": os.path.basename(p),
            "n_points": len(ys),
            "peak": peak,
            "peak_index": ys.index(peak),
            "peak_pos_frac": round(ys.index(peak) / max(1, len(ys) - 1), 4),
            "end_value": ys[-1],
            "max_plateau_run": sat_run(ys),
            "content_sha256_1MB": sha256_of(p),
        }
        traces.append(rec)
    # 重复曲线：内容 hash 分组
    groups = {}
    for t in traces:
        groups.setdefault(t["content_sha256_1MB"], []).append(t["file"])
    dup_groups = [sorted(g) for g in groups.values() if len(g) > 1]
    peaks = [t["peak"] for t in traces]
    lo, hi, flags = iqr_flags(peaks)
    outliers = [t["file"] for t, f in zip(traces, flags) if f]
    saturated = [t["file"] for t in traces if t["max_plateau_run"] >= 5]
    return {
        "n_traces": len(traces),
        "peak_stats": {"mean": mean(peaks), "std": pstdev(peaks),
                       "min": min(peaks) if peaks else None,
                       "max": max(peaks) if peaks else None,
                       "iqr_lo": lo, "iqr_hi": hi},
        "peak_outlier_traces": outliers,
        "saturated_traces(plateau>=5)": saturated,
        "duplicate_trace_groups": dup_groups,
        "per_trace": traces[:400],
        "thresholds": {"outlier": "峰值 IQR×1.5 (Tukey)", "saturation": "相同读数连续段>=5",
                       "duplicate": "文件内容 sha256 完全相同"},
    }


def _coerce_matrix(text):
    """从文本中找 5 行 × 2 列（或 2 行 × 5 列）的 0..1 或 0..100 数值矩阵。"""
    rows = []
    for line in text.splitlines():
        vals = [float(x) for x in NUM_RE.findall(line)]
        vals = [v for v in vals if 0.0 <= v <= 100.0]
        if len(vals) >= 2:
            rows.append(vals)
    cand = []
    for i in range(0, max(0, len(rows) - 4)):
        block = rows[i:i + 5]
        if all(len(r) >= 2 for r in block):
            cand.append([r[:2] for r in block])
    return cand


def check_iris(files):
    mats = []
    for p in files:
        if os.path.splitext(p)[1].lower() not in (".txt", ".csv", ".md", ".json"):
            continue
        text = read_text(p)
        if "iris" not in (os.path.basename(p).lower() + text[:2000].lower()) \
                and "estimator" not in text.lower() and "split" not in text.lower():
            continue
        for m in _coerce_matrix(text):
            mats.append({"file": os.path.basename(p), "matrix_5x2": m})
    findings = {"candidate_matrices": mats, "estimator_stats": []}
    if mats:
        m = mats[0]["matrix_5x2"]
        for col in range(2):
            vals = [row[col] for row in m]
            findings["estimator_stats"].append({
                "estimator_col": col,
                "split_values": vals,
                "mean": mean(vals), "std": pstdev(vals),
                "min": min(vals), "max": max(vals)})
        diffs = [row[0] - row[1] for row in m]
        findings["per_split_diff_col0_minus_col1"] = diffs
        findings["sign_consistent"] = all(d > 0 for d in diffs) or all(d < 0 for d in diffs)
        findings["thresholds"] = {"matrix": "5 split × 2 estimator, 取值 0..100 或 0..1"}
    else:
        findings["note"] = "未在文本材料中找到显式 5×2 数值矩阵；需人工定位 split×estimator 表"
    return findings


def check_cefixime(files, work_dir=None):
    out = {"workbooks": [], "pdf_cross_hits": [], "unit_tokens": {}}
    pdf_text = ""
    for p in files:
        ext = os.path.splitext(p)[1].lower()
        if ext == ".xlsx":
            out["workbooks"].append(xlsx_inventory(p))
        elif ext == ".pdf" and work_dir:
            txt_path = os.path.join(work_dir, os.path.basename(p) + ".txt")
            rc = os.system("pdftotext %s %s 2>/dev/null" % (p, txt_path))
            if rc == 0 and os.path.exists(txt_path):
                pdf_text += "\n" + read_text(txt_path)
    # 单位记号统计（歧义登记）
    units = re.findall(r"(mg/mL|mg/L|µg/mL|ug/mL|μg/mL|%|MPa|mg|mL|h|min)", pdf_text)
    for u in units:
        out["unit_tokens"][u] = out["unit_tokens"].get(u, 0) + 1
    # 交叉命中：工作簿样本数值出现在 PDF 文本中
    if pdf_text and out["workbooks"]:
        pdf_nums = set(re.findall(r"\d+\.\d+", pdf_text))
        hits = []
        for wb in out["workbooks"]:
            for sh in wb.get("sheets", []):
                for v in sh.get("numeric_samples", []):
                    s = ("%.4f" % v).rstrip("0").rstrip(".")
                    if "." in s and s in pdf_nums:
                        hits.append({"sheet": sh["name"], "value": v})
        out["pdf_cross_hits"] = hits[:100]
        out["cross_hit_count"] = len(hits)
    out["thresholds"] = {"cross_hit": "工作簿数值(小数形式)精确出现于 PDF 文本"}
    return out


def check_generic(files):
    tables = []
    for p in files:
        if os.path.splitext(p)[1].lower() not in (".csv", ".txt"):
            continue
        xs, ys = parse_xy_trace(p)
        if len(ys) >= 3:
            tables.append({"file": os.path.basename(p), "n_rows": len(ys),
                           "col2_mean": mean(ys), "col2_std": pstdev(ys),
                           "col2_min": min(ys), "col2_max": max(ys)})
    return {"tables": tables, "note": "通用兜底：仅列级描述统计，判读需 Agent 结合 task.md 完成"}


CHECKERS = {"bending_traces": check_bending,
            "iris_computational": check_iris,
            "cefixime_workbook": check_cefixime,
            "generic": check_generic}


def run(input_dir, work_dir=None):
    arch, evidence, files = detect(input_dir)
    checker = CHECKERS[arch]
    if arch == "cefixime_workbook":
        findings = checker(files, work_dir=work_dir)
    else:
        findings = checker(files)
    return {"archetype": arch, "detection_evidence": evidence, "findings": findings}
