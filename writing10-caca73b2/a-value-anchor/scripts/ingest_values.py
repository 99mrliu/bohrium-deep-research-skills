#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ingest_values.py — 材料数值台账构建器（value-anchor-rd）

递归扫描材料目录，确定性提取数值，生成 values.json（机器可读台账）与
values_report.md（人读台账）。不调用任何模型。

识别三类来源：
  (a) CSV/TSV 表格：csv 模块嗅探分隔符，首行非数值判定表头；
      数值单元格支持 "12.3" 与 "12.3 ± 1.2" 两种写法。
  (b) 纯文本统计输出（.txt/.md/.log/.out）：正则识别
      p = 0.032 / p < 0.05 / mean ± SD / 95% CI [a, b] / n = 12 /
      t(18) = 2.31 / F(2, 33) = 4.56 / r = 0.42 等。
  (c) 图注文本：路径含 caption / 图注 / fig（不区分大小写）的 .txt/.md，
      抽取含"数值+单位"的片段为 caption_value（confidence=medium）。

values.json 条目字段：
  id, kind(table_cell|stat|caption_value), value, unit,
  error{kind: SD|SEM|CI95|none|unknown, value},
  stat(p|n|t|F|r|mean_sd|CI95|null), source{file,line,row,col},
  method(table-parse|regex|caption-parse), confidence(high|medium), note

无法读取/解码的文件记入 skipped，不中断、不崩溃。
"""

import argparse
import csv
import json
import os
import re
import sys

# ---------------------------------------------------------------- 正则模式
NUM = r"-?\d+(?:\.\d+)?"

PATTERNS = [
    # (stat 名, 正则, 说明)；CI 须先于 mean_sd 匹配以免区间端点被拆走
    ("CI95", re.compile(
        r"95%%\s*(?:CI|置信区间)\s*[\[\(]\s*(%s)\s*[,，;；]\s*(%s)\s*[\]\)]"
        % (NUM, NUM), re.I), "95% 置信区间"),
    ("mean_sd", re.compile(
        r"(%s)\s*±\s*(%s)" % (NUM, NUM)), "均值 ± 误差"),
    ("t", re.compile(
        r"\bt\s*\(\s*(%s)\s*\)\s*=\s*(%s)" % (NUM, NUM)), "t 统计量"),
    ("F", re.compile(
        r"\bF\s*\(\s*(%s)\s*[,，]\s*(%s)\s*\)\s*=\s*(%s)"
        % (NUM, NUM, NUM)), "F 统计量"),
    ("p", re.compile(
        r"\bp\s*([<=>≤≥])\s*(0?\.\d+)", re.I), "p 值"),
    ("n", re.compile(r"\bn\s*=\s*(\d+)"), "样本量"),
    ("alpha", re.compile(r"\balpha\s*=\s*(0?\.\d+)", re.I), "显著性水平"),
    ("r", re.compile(r"\br\s*=\s*(%s)" % NUM), "相关系数"),
]

# 单位词表（长的在前，避免 mL 被 L 截断）；caption-parse 使用
UNITS = ["mmol/L", "µmol/L", "μmol/L", "mol/L", "mg/mL", "µg/mL", "μg/mL",
         "ng/mL", "g/L", "mg/L", "mmHg", "mM", "µM", "μM", "nM",
         "mg/kg", "g/kg", "mL/min", "kg/m2", "kg/m²",
         "cm", "mm", "kg", "mg", "µg", "μg", "ng", "mL", "µL", "μL",
         "min", "sec", "Hz", "%", "h", "s", "g"]
UNIT_RE = "|".join(re.escape(u) for u in UNITS)
CAPTION_NUM_RE = re.compile(r"(%s)\s*(%s)\b" % (NUM, UNIT_RE))

TABLE_EXTS = {".csv", ".tsv"}
TEXT_EXTS = {".txt", ".md", ".log", ".out"}
CAPTION_HINTS = ("caption", "图注", "fig")


def _is_caption_path(relpath):
    low = relpath.lower()
    return any(h in low for h in CAPTION_HINTS)


def _sniff_delimiter(sample, ext):
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;")
        return dialect.delimiter
    except csv.Error:
        return "\t" if ext == ".tsv" else ","


_CELL_NUM_RE = re.compile(
    r"^\s*(%s)(?:\s*±\s*(%s))?\s*$" % (NUM, NUM))


def _parse_cell(text):
    """返回 (value, err) 或 None；err 为 None 表示无 ± 部分。"""
    m = _CELL_NUM_RE.match(text or "")
    if not m:
        return None
    return float(m.group(1)), (float(m.group(2)) if m.group(2) else None)


def _row_has_header(row):
    """该行含任何非数值、非空单元格则视为表头行。"""
    for c in row:
        c = (c or "").strip()
        if c and _parse_cell(c) is None:
            return True
    return False


# ---------------------------------------------------------------- 台账条目
class Ledger:
    def __init__(self):
        self.entries = []
        self.skipped = []
        self._n = 0

    def add(self, kind, value, unit, err_kind, err_value, stat,
            src_file, line=None, row=None, col=None,
            method="regex", confidence="high", note=""):
        self._n += 1
        self.entries.append({
            "id": "V%02d" % self._n,
            "kind": kind,
            "value": value,
            "unit": unit,
            "error": {"kind": err_kind, "value": err_value},
            "stat": stat,
            "source": {"file": src_file, "line": line, "row": row, "col": col},
            "method": method,
            "confidence": confidence,
            "note": note,
        })

    def skip(self, relpath, reason):
        self.skipped.append({"file": relpath, "reason": reason})


# ---------------------------------------------------------------- 表格解析
def parse_table(path, relpath, ledger):
    ext = os.path.splitext(path)[1].lower()
    try:
        with open(path, "r", encoding="utf-8-sig", newline="") as f:
            sample = f.read(4096)
            f.seek(0)
            delim = _sniff_delimiter(sample, ext)
            rows = [r for r in csv.reader(f, delimiter=delim) if any(
                (c or "").strip() for c in r)]
    except (UnicodeDecodeError, OSError) as e:
        ledger.skip(relpath, "表格读取失败: %s" % e)
        return
    if not rows:
        ledger.skip(relpath, "表格为空")
        return

    header = rows[0] if _row_has_header(rows[0]) else None
    data_rows = rows[1:] if header else rows

    for i, row in enumerate(data_rows):
        row_no = (i + 2) if header else (i + 1)  # 1 起始的物理行号
        for j, cell in enumerate(row):
            parsed = _parse_cell(cell)
            if parsed is None:
                continue
            value, err = parsed
            col_name = (header[j].strip() if header and j < len(header)
                        and header[j].strip() else "col%d" % (j + 1))
            # 误差类型：列名含 SD/SEM 时该列本身即误差列
            col_low = col_name.lower()
            if col_low in ("sd", "std", "standard deviation"):
                stat, err_kind, err_val = "SD", "none", None
                note = "该单元格本身为标准差列数值"
            elif col_low in ("sem", "se", "standard error"):
                stat, err_kind, err_val = "SEM", "none", None
                note = "该单元格本身为标准误列数值"
            elif err is not None:
                stat, err_kind, err_val = "mean_sd", "unknown", err
                note = "单元格内 ± 误差，列名未注明误差类型"
            else:
                stat, err_kind, err_val = None, "none", None
                note = ""
            ledger.add(
                kind="table_cell", value=value, unit=None,
                err_kind=err_kind, err_value=err_val, stat=stat,
                src_file=relpath, row=row_no, col=col_name,
                method="table-parse", confidence="high", note=note)


# ---------------------------------------------------------------- 文本解析
def _error_kind_from_line(line):
    """由整行上下文推断 ± 误差类型；未注明返回 unknown。"""
    if re.search(r"\bSD\b|标准差", line):
        return "SD"
    if re.search(r"\bSEM?\b|标准误", line):
        return "SEM"
    return "unknown"


def parse_text(path, relpath, is_caption, ledger):
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
    except (UnicodeDecodeError, OSError) as e:
        ledger.skip(relpath, "文本读取失败（可能为二进制或乱码）: %s" % e)
        return

    for ln, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        claimed = []  # 已被统计模式占用的字符区间，供 caption 阶段跳过
        for stat, rx, desc in PATTERNS:
            for m in rx.finditer(line):
                claimed.append(m.span())
                g = m.groups()
                if stat == "CI95":
                    ledger.add(
                        kind="stat", value=[float(g[0]), float(g[1])],
                        unit=None, err_kind="CI95", err_value=None,
                        stat="CI95", src_file=relpath, line=ln,
                        method="regex", confidence="high",
                        note="%s: %s" % (desc, m.group(0)))
                elif stat == "mean_sd":
                    ek = _error_kind_from_line(line)
                    um = re.match(r"\s*(%s)\b" % UNIT_RE, line[m.end():])
                    ledger.add(
                        kind="stat", value=float(g[0]),
                        unit=um.group(1) if um else None,
                        err_kind=ek, err_value=float(g[1]),
                        stat="mean_sd", src_file=relpath, line=ln,
                        method="regex", confidence="high",
                        note="%s（误差类型: %s）: %s" % (desc, ek, m.group(0)))
                elif stat == "t":
                    ledger.add(
                        kind="stat", value=float(g[1]), unit=None,
                        err_kind="none", err_value=None, stat="t",
                        src_file=relpath, line=ln, method="regex",
                        confidence="high",
                        note="t(df=%s): %s" % (g[0], m.group(0)))
                elif stat == "F":
                    ledger.add(
                        kind="stat", value=float(g[2]), unit=None,
                        err_kind="none", err_value=None, stat="F",
                        src_file=relpath, line=ln, method="regex",
                        confidence="high",
                        note="F(df=%s,%s): %s" % (g[0], g[1], m.group(0)))
                elif stat == "p":
                    ledger.add(
                        kind="stat", value=float(g[1]), unit=None,
                        err_kind="none", err_value=None, stat="p",
                        src_file=relpath, line=ln, method="regex",
                        confidence="high",
                        note="p 值（比较符 %s）: %s" % (g[0], m.group(0)))
                elif stat == "n":
                    ledger.add(
                        kind="stat", value=int(g[0]), unit=None,
                        err_kind="none", err_value=None, stat="n",
                        src_file=relpath, line=ln, method="regex",
                        confidence="high", note="样本量: %s" % m.group(0))
                elif stat == "r":
                    ledger.add(
                        kind="stat", value=float(g[0]), unit=None,
                        err_kind="none", err_value=None, stat="r",
                        src_file=relpath, line=ln, method="regex",
                        confidence="high", note="相关系数: %s" % m.group(0))
                elif stat == "alpha":
                    ledger.add(
                        kind="stat", value=float(g[0]), unit=None,
                        err_kind="none", err_value=None, stat="alpha",
                        src_file=relpath, line=ln, method="regex",
                        confidence="high", note="显著性水平: %s" % m.group(0))
        # 带单位数值：图注文件记 caption_value(medium)，其余文本记 stat(high)
        for m in CAPTION_NUM_RE.finditer(line):
            if any(s <= m.start() < e or s < m.end() <= e
                   for s, e in claimed):
                continue  # 该数值已被统计模式收录，避免重复
            if is_caption:
                ledger.add(
                    kind="caption_value", value=float(m.group(1)),
                    unit=m.group(2), err_kind="none", err_value=None,
                    stat=None, src_file=relpath, line=ln,
                    method="caption-parse", confidence="medium",
                    note="图注数值: %s" % m.group(0))
            else:
                ledger.add(
                    kind="stat", value=float(m.group(1)),
                    unit=m.group(2), err_kind="none", err_value=None,
                    stat=None, src_file=relpath, line=ln,
                    method="regex", confidence="high",
                    note="带单位数值: %s" % m.group(0))


# ---------------------------------------------------------------- 主流程
def build_ledger(materials_dir):
    ledger = Ledger()
    for root, dirs, files in os.walk(materials_dir):
        dirs.sort()
        for name in sorted(files):
            path = os.path.join(root, name)
            rel = os.path.relpath(path, materials_dir)
            ext = os.path.splitext(name)[1].lower()
            if ext in TABLE_EXTS:
                parse_table(path, rel, ledger)
            elif ext in TEXT_EXTS:
                parse_text(path, rel, _is_caption_path(rel), ledger)
            else:
                ledger.skip(rel, "不支持的扩展名（可能为二进制材料，"
                                 "请先用 pdftotext 等工具转为文本后重扫）")
    return ledger


def render_report(ledger, materials_dir):
    out = ["# 数值台账报告（values_report.md）", "",
           "- 材料目录: `%s`" % materials_dir,
           "- 条目总数: %d" % len(ledger.entries),
           "- 跳过文件: %d" % len(ledger.skipped),
           "- 生成器: ingest_values.py（确定性，无模型调用）", "",
           "| id | kind | value | unit | error | stat | source | method | confidence | note |",
           "|----|------|-------|------|-------|------|--------|--------|------------|------|"]
    for e in ledger.entries:
        err = e["error"]
        err_s = "%s:%s" % (err["kind"], err["value"]) if err["value"] is not None else err["kind"]
        src = e["source"]
        loc = src["file"]
        if src["line"]:
            loc += ":L%s" % src["line"]
        if src["row"]:
            loc += ":R%s/%s" % (src["row"], src["col"])
        val = e["value"]
        val_s = "[%s, %s]" % (val[0], val[1]) if isinstance(val, list) else str(val)
        out.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            e["id"], e["kind"], val_s, e["unit"] or "-", err_s,
            e["stat"] or "-", loc, e["method"], e["confidence"],
            (e["note"] or "").replace("|", "\\|")))
    if ledger.skipped:
        out += ["", "## skipped（未纳入台账的文件）", ""]
        for s in ledger.skipped:
            out.append("- `%s` — %s" % (s["file"], s["reason"]))
    out.append("")
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="ingest_values.py",
        description="扫描材料目录，构建数值台账 values.json 与 values_report.md")
    ap.add_argument("--materials", required=True, help="材料目录（递归扫描）")
    ap.add_argument("--out", required=True, help="输出 values.json 路径")
    ap.add_argument("--report", default=None,
                    help="输出 values_report.md 路径（默认与 --out 同目录）")
    args = ap.parse_args(argv)

    if not os.path.isdir(args.materials):
        print("FAIL: 材料目录不存在: %s" % args.materials)
        return 1

    ledger = build_ledger(args.materials)
    payload = {
        "generated_by": "ingest_values.py (value-anchor-rd)",
        "materials_dir": os.path.abspath(args.materials),
        "entry_count": len(ledger.entries),
        "entries": ledger.entries,
        "skipped": ledger.skipped,
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")
    report_path = args.report or os.path.join(
        os.path.dirname(os.path.abspath(args.out)), "values_report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(render_report(ledger, args.materials))
    print("INGEST OK: 条目 %d，跳过 %d -> %s ; 报告 -> %s"
          % (len(ledger.entries), len(ledger.skipped), args.out, report_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
