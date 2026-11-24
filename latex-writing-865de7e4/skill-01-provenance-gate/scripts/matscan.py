#!/usr/bin/env python3
"""matscan.py — 材料清点与事实抽取（事实来源闸门·第 1 步）。

仅做确定性机械工作：清点 /input 材料，把数字+单位、百分比、样本量、术语、
引用键、图表标题抽取为带「文件:行号」锚点的事实条目。不做任何语义判断。

用法:
    python3 matscan.py --input /input --work /app/work

产出:
    <work>/facts/facts.jsonl          每行一条事实: {id, type, value, unit,
                                      anchor, line_text}
    <work>/facts/materials_index.md   材料总览（含 gaps 段）
    <work>/facts/extraction_report.json  降级与统计记录

支持材料: .md/.txt/.csv/.tex/.bib 直接读；.pdf 用 pdftotext（可选增强，
缺失时记 gaps 并继续）。PDF 条目以页码作为行锚点（anchor 形如 file.pdf:p3）。
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys

TEXT_EXTS = {".md", ".txt", ".csv", ".tex", ".bib"}
SKIP_DIRS = {".git", "__pycache__"}

# 数字+单位：数值后紧跟（可隔一个空格）单位串
NUM_UNIT_RE = re.compile(
    r"(?<![\w.])(\d+(?:\.\d+)?)(?:\s?)"
    r"(m/s|km/h|kg|mg|kDa|Da|mol|mM|uM|µM|nM|mL|uL|µL|nm|mm|cm|km|"
    r"ms|s|min|h|K|Pa|kPa|MPa|GPa|eV|keV|MeV|GeV|Hz|kHz|MHz|GHz|"
    r"degC|°C|°F|V|mV|A|mA|W|kW|J|kJ|N)\b"
)
PERCENT_RE = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)\s?%")
SAMPLE_RE = re.compile(r"\b[nN]\s?=\s?(\d+)\b")
CITE_RE = re.compile(r"\\cite[t|p|alp|num|yearpar|s]*\{([^}]*)\}")
BIBKEY_RE = re.compile(r"@\w+\s*\{\s*([^,\s]+)")
CAPTION_RE = re.compile(r"\\caption\{([^}]*)\}", re.S)
TERM_RES = [
    re.compile(r"\\newglossaryentry\{([^}]*)\}"),
    re.compile(r"\\newacronym(?:\[[^\]]*\])?\{([^}]*)\}"),
    re.compile(r"\\newcommand\{\\([A-Za-z]+)\}"),
]
# 术语候选：拉丁二名法、含连字符的复合术语（如 N-heterocyclic carbene）
TERM_TEXT_RES = [
    re.compile(r"\b[A-Z][a-z]{2,}\s[a-z]{3,}\b"),  # E. coli / Homo sapiens 类
]


def eprint(*a):
    print(*a, file=sys.stderr)


def safe_read(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError as e:
        return None


def norm_path(p, base):
    """相对 base 的路径，供锚点使用。"""
    try:
        return os.path.relpath(p, base)
    except ValueError:
        return p


class FactSink:
    def __init__(self):
        self.facts = []
        self._n = 0

    def add(self, ftype, value, unit, anchor, line_text):
        self._n += 1
        self.facts.append({
            "id": "F%04d" % self._n,
            "type": ftype,
            "value": value.strip(),
            "unit": unit or "",
            "anchor": anchor,
            "line_text": line_text.strip()[:300],
        })


def scan_lines(sink, rel, lines, anchor_fmt):
    """对一组行做通用抽取。anchor_fmt: 'L' -> file:行号；'P' -> file:p页码。"""
    for i, line in enumerate(lines, 1):
        anchor = "%s:%d" % (rel, i) if anchor_fmt == "L" else "%s:p%d" % (rel, i)
        for m in NUM_UNIT_RE.finditer(line):
            sink.add("num_unit", m.group(1), m.group(2), anchor, line)
        for m in PERCENT_RE.finditer(line):
            sink.add("percent", m.group(1), "%", anchor, line)
        for m in SAMPLE_RE.finditer(line):
            sink.add("sample_size", m.group(1), "n", anchor, line)
        for m in CITE_RE.finditer(line):
            for key in m.group(1).split(","):
                if key.strip():
                    sink.add("cite_key", key.strip(), "", anchor, line)
        for m in CAPTION_RE.finditer(line):
            cap = " ".join(m.group(1).split())
            if cap:
                sink.add("caption", cap[:120], "", anchor, line)
        for rx in TERM_RES:
            for m in rx.finditer(line):
                sink.add("term", m.group(1), "", anchor, line)


def scan_bib(sink, rel, text):
    for m in BIBKEY_RE.finditer(text):
        # bib 键锚点取键所在行号
        lineno = text.count("\n", 0, m.start()) + 1
        sink.add("bib_key", m.group(1).strip(), "", "%s:%d" % (rel, lineno),
                 m.group(0)[:120])


def scan_csv(sink, rel, lines):
    """CSV 额外把每个数值单元格抽为 data_value，锚点 file:行号。"""
    import csv
    import io
    text = "\n".join(lines)
    try:
        rows = list(csv.reader(io.StringIO(text)))
    except csv.Error:
        return
    for r, row in enumerate(rows, 1):
        for cell in row:
            c = cell.strip()
            if re.fullmatch(r"-?\d+(\.\d+)?([eE][+-]?\d+)?", c):
                sink.add("data_value", c, "", "%s:%d" % (rel, r),
                         " | ".join(x.strip() for x in row)[:300])


def discover_materials(input_dir, case, gaps, notes):
    """返回材料绝对路径列表。case.json 指向优先，缺失记 gap 并降级遍历。"""
    found = []
    seen = set()

    def add(p, origin):
        ap = os.path.abspath(p)
        if ap in seen:
            return
        seen.add(ap)
        if os.path.isfile(ap):
            found.append(ap)
        else:
            gaps.append("材料路径不存在（%s 指向）: %s" % (origin, p))

    if case is not None:
        # 常见材料字段；值可为字符串或列表，路径相对 /input
        for field in ("materials", "files", "inputs", "references", "attachments"):
            v = case.get(field)
            if isinstance(v, str):
                v = [v]
            if isinstance(v, list):
                for item in v:
                    if isinstance(item, str):
                        add(os.path.join(input_dir, item), "case.json:%s" % field)
        # 顶层单文件字段
        for field in ("draft", "manuscript", "paper", "bib", "data", "notes"):
            v = case.get(field)
            if isinstance(v, str):
                add(os.path.join(input_dir, v), "case.json:%s" % field)
        # task.md 本身也作为材料（任务口径的来源）
        if isinstance(case.get("task"), str):
            add(os.path.join(input_dir, case["task"]), "case.json:task")

    if not found:
        if case is None:
            notes.append("case.json 缺失或不可解析，降级为遍历 /input")
        else:
            notes.append("case.json 未指向有效材料，降级为遍历 /input")
        for root, dirs, fnames in os.walk(input_dir):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for fn in sorted(fnames):
                ap = os.path.join(root, fn)
                if os.path.splitext(fn)[1].lower() in TEXT_EXTS | {".pdf"}:
                    add(ap, "walk")
    return found


def main():
    ap = argparse.ArgumentParser(description="材料清点与事实抽取")
    ap.add_argument("--input", default="/input")
    ap.add_argument("--work", default="/app/work")
    args = ap.parse_args()

    facts_dir = os.path.join(args.work, "facts")
    os.makedirs(facts_dir, exist_ok=True)

    gaps, notes = [], []
    report = {
        "input_dir": os.path.abspath(args.input),
        "pdftotext": None,
        "materials_scanned": [],
        "gaps": gaps,
        "notes": notes,
        "fact_counts": {},
    }

    # 读取 case.json（可选）
    case = None
    case_path = os.path.join(args.input, "case.json")
    raw = safe_read(case_path)
    if raw is None:
        notes.append("未找到 case.json: %s" % case_path)
    else:
        try:
            case = json.loads(raw)
        except json.JSONDecodeError as e:
            notes.append("case.json 解析失败（%s），按缺失处理" % e)
            case = None

    if not os.path.isdir(args.input):
        gaps.append("输入目录不存在: %s" % args.input)

    pdftotext = shutil.which("pdftotext")
    report["pdftotext"] = pdftotext or "MISSING"
    if pdftotext is None:
        notes.append("pdftotext 不在 PATH，PDF 材料将记入 gaps 降级处理")

    sink = FactSink()
    materials = discover_materials(args.input, case, gaps, notes) \
        if os.path.isdir(args.input) else []

    for path in materials:
        rel = norm_path(path, args.input)
        ext = os.path.splitext(path)[1].lower()
        entry = {"file": rel, "ext": ext, "facts": 0, "status": "ok"}
        if ext == ".pdf":
            if pdftotext is None:
                entry["status"] = "gap"
                gaps.append("无法提取 PDF 文本（pdftotext 缺失）: %s" % rel)
            else:
                try:
                    out = subprocess.run(
                        [pdftotext, "-layout", path, "-"],
                        capture_output=True, text=True, timeout=60)
                    if out.returncode == 0:
                        pages = out.stdout.split("\f")
                        before = len(sink.facts)
                        for pno, page in enumerate(pages, 1):
                            scan_lines(sink, rel, page.splitlines(), "P")
                        entry["facts"] = len(sink.facts) - before
                        entry["pages"] = len(pages)
                        entry["anchor_note"] = "PDF 条目锚点以页码代行号"
                    else:
                        entry["status"] = "gap"
                        gaps.append("pdftotext 失败（rc=%d）: %s"
                                    % (out.returncode, rel))
                except (OSError, subprocess.TimeoutExpired) as e:
                    entry["status"] = "gap"
                    gaps.append("pdftotext 调用异常（%s）: %s" % (e, rel))
        elif ext in TEXT_EXTS:
            text = safe_read(path)
            if text is None:
                entry["status"] = "gap"
                gaps.append("文件不可读: %s" % rel)
            else:
                lines = text.splitlines()
                before = len(sink.facts)
                scan_lines(sink, rel, lines, "L")
                if ext == ".bib":
                    scan_bib(sink, rel, text)
                if ext == ".csv":
                    scan_csv(sink, rel, lines)
                entry["facts"] = len(sink.facts) - before
                entry["lines"] = len(lines)
        else:
            entry["status"] = "skipped"
            notes.append("暂不支持的扩展名，跳过: %s" % rel)
        report["materials_scanned"].append(entry)

    # 写 facts.jsonl
    facts_path = os.path.join(facts_dir, "facts.jsonl")
    with open(facts_path, "w", encoding="utf-8") as f:
        for fact in sink.facts:
            f.write(json.dumps(fact, ensure_ascii=False) + "\n")

    counts = {}
    for fact in sink.facts:
        counts[fact["type"]] = counts.get(fact["type"], 0) + 1
    report["fact_counts"] = counts
    report["total_facts"] = len(sink.facts)

    # 写 materials_index.md
    idx = ["# 材料总览（materials_index）", "",
           "输入目录：`%s`" % report["input_dir"],
           "pdftotext：`%s`" % report["pdftotext"], "",
           "## 材料清单", "",
           "| 文件 | 类型 | 状态 | 抽取事实数 | 备注 |",
           "| --- | --- | --- | --- | --- |"]
    for m in report["materials_scanned"]:
        note = m.get("anchor_note", "")
        if "lines" in m:
            note = (note + " " if note else "") + "%d 行" % m["lines"]
        if "pages" in m:
            note = (note + " " if note else "") + "%d 页" % m["pages"]
        idx.append("| %s | %s | %s | %d | %s |" %
                   (m["file"], m["ext"], m["status"], m["facts"], note or "—"))
    idx += ["", "## 事实统计", ""]
    for t, c in sorted(counts.items()):
        idx.append("- %s: %d" % (t, c))
    idx.append("- 合计: %d" % len(sink.facts))
    idx += ["", "## gaps（缺口与降级记录）", ""]
    if gaps:
        for g in gaps:
            idx.append("- %s" % g)
    else:
        idx.append("- （无）")
    if notes:
        idx += ["", "## 运行备注", ""]
        for n in notes:
            idx.append("- %s" % n)
    idx.append("")
    with open(os.path.join(facts_dir, "materials_index.md"), "w",
              encoding="utf-8") as f:
        f.write("\n".join(idx))

    with open(os.path.join(facts_dir, "extraction_report.json"), "w",
              encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print("matscan: 材料 %d 个，事实 %d 条，gap %d 条 -> %s"
          % (len(report["materials_scanned"]), len(sink.facts),
             len(gaps), facts_dir))
    return 0


if __name__ == "__main__":
    sys.exit(main())
