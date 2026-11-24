#!/usr/bin/env python3
"""numeric_scan.py — 跨位置数值一致性确定性扫描（bundle-b）

从 /input 材料抽取文本（md/txt/tex 直读，docx 用 zipfile+XML 去标签，
pdf 尝试 pdftotext），正则抽取"数值提及"（%、±、单位、n=、p 值、倍数、
率类小数），按就近关键词聚类同一物理量，跨小节比对：同一量出现 ≥2 个
不同值且超出舍入容差 → 候选不一致 finding（带小节/行号/逐字引用）。

输出：work/numeric_report.json 与 work/numeric_report.md。
另：若 /app/output/result.json 尚不存在，先写保底 partial result.json
（运行时契约：第一次脚本调用即产出保底结果）。

退出码：0 成功；非 0 失败并打印原因到 stderr。
仅使用 Python 3 标准库。
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

VERSION = "1.0.0"

DEFAULT_CONTRACT = ["case_id", "status", "review_report", "findings",
                    "sources", "uncertainty", "change_log"]

TEXT_EXT = {".md", ".txt", ".tex", ".csv"}
SKIP_FILES = {"case.json", "task.md", "answers.json"}

# ---------------- 文本抽取 ----------------

def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def extract_pdf(path):
    """返回 (text, note)。note 为 None 表示成功。"""
    exe = shutil.which("pdftotext")
    if not exe:
        return "", "extract_error: pdftotext 不可用，PDF 未抽取"
    try:
        r = subprocess.run([exe, "-layout", path, "-"],
                           capture_output=True, timeout=120)
        text = r.stdout.decode("utf-8", errors="replace")
        if r.returncode != 0:
            return text, "extract_error: pdftotext 退出码 %d" % r.returncode
        return text, None
    except Exception as e:  # noqa: BLE001
        return "", "extract_error: pdftotext 调用失败: %s" % e


def extract_docx(path):
    try:
        with zipfile.ZipFile(path) as z:
            xml = z.read("word/document.xml").decode("utf-8", errors="replace")
        xml = re.sub(r"</w:p>", "\n", xml)
        return re.sub(r"<[^>]+>", "", xml), None
    except Exception as e:  # noqa: BLE001
        return "", "extract_error: docx 解析失败: %s" % e


def extract_material(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in TEXT_EXT:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read(), None
    if ext == ".pdf":
        return extract_pdf(path)
    if ext == ".docx":
        return extract_docx(path)
    return "", "extract_error: 不支持的扩展名 %s" % ext

# ---------------- 小节切分 ----------------

MD_HEAD = re.compile(r"^(#{1,6})\s*(.+?)\s*#*\s*$")
PLAIN_HEAD = re.compile(
    r"^(摘要|abstract|关键词|keywords|引言|introduction|背景|background|"
    r"方法|methods?|材料与方法|materials and methods|实验|experiments?|"
    r"结果|results?|讨论|discussion|结论|conclusions?|参考文献|references|"
    r"bibliography)\s*[:：]?\s*$", re.I)
CAPTION_HEAD = re.compile(
    r"^(图\s*\d+|figure\s*\d+|fig\.?\s*\d+|表\s*\d+|table\s*\d+)\s*[:：.]",
    re.I)


def split_sections(text):
    """按 markdown 标题 / 常见小节词 / 图表标题切分。
    返回 [(section_name, start_line, [ (line_no, line_text) ... ])]"""
    lines = text.splitlines()
    sections = []
    cur_name, cur_start, cur_lines = "正文(开头)", 1, []
    for i, line in enumerate(lines, start=1):
        stripped = line.strip()
        m = MD_HEAD.match(stripped)
        name = None
        if m:
            name = m.group(2).strip()
        elif PLAIN_HEAD.match(stripped):
            name = stripped.rstrip("[:：]").strip()
        elif CAPTION_HEAD.match(stripped):
            name = "图表标题: " + stripped[:40]
        if name is not None:
            if cur_lines or not sections:
                sections.append((cur_name, cur_start, cur_lines))
            cur_name, cur_start, cur_lines = name, i, []
        else:
            cur_lines.append((i, line))
    sections.append((cur_name, cur_start, cur_lines))
    return [s for s in sections if s[2] or s[0] != "正文(开头)"]

# ---------------- 数值提及抽取 ----------------

NUM = r"(\d+(?:\.\d+)?)"
UNIT_ALT = (r"ms|min|µs|us|s|h|kg|mg|µg|ug|g|km|cm|mm|µm|um|nm|m|"
            r"kHz|MHz|GHz|Hz|KB|MB|GB|TB|kPa|MPa|Pa|mmol|mol|mL|µL|uL|L|"
            r"mV|kV|V|mA|A|kW|W|kJ|J|eV|dB|rpm|°C|K")

PATTERNS = [
    ("sample_size", re.compile(r"\b[nN]\s*=\s*(\d{1,7})\b"), None),
    ("pvalue", re.compile(r"\bp\s*([<≤=>≥]{1,2})\s*(0?\.\d+)\b"), None),
    ("pm", re.compile(NUM + r"\s*(?:±|\+/-|\+／-)\s*" + NUM +
                      r"\s*(%|(?:" + UNIT_ALT + r"))?\b"), None),
    ("percent", re.compile(NUM + r"\s*[%％]"), None),
    ("unit", re.compile(NUM + r"\s*(" + UNIT_ALT + r")\b"), None),
    ("fold", re.compile(NUM + r"\s*(?:倍|×)"), None),
    ("rate_frac", re.compile(
        r"([\u4e00-\u9fffA-Za-z\-]{2,12}?)\s*(?:为|是|达|达到|of|:|：)\s*"
        r"(0\.\d{2,4})\b"), None),
]

UNIT_FAMILY = {
    "ms": ("time", 1e-3), "s": ("time", 1.0), "min": ("time", 60.0),
    "h": ("time", 3600.0), "µs": ("time", 1e-6), "us": ("time", 1e-6),
    "km": ("length", 1e3), "m": ("length", 1.0), "cm": ("length", 1e-2),
    "mm": ("length", 1e-3), "µm": ("length", 1e-6), "um": ("length", 1e-6),
    "nm": ("length", 1e-9),
    "kg": ("mass", 1e3), "g": ("mass", 1.0), "mg": ("mass", 1e-3),
    "µg": ("mass", 1e-6), "ug": ("mass", 1e-6),
    "Hz": ("freq", 1.0), "kHz": ("freq", 1e3), "MHz": ("freq", 1e6),
    "GHz": ("freq", 1e9),
    "KB": ("data", 1e3), "MB": ("data", 1e6), "GB": ("data", 1e9),
    "TB": ("data", 1e12),
    "Pa": ("pressure", 1.0), "kPa": ("pressure", 1e3),
    "MPa": ("pressure", 1e6),
    "mol": ("amount", 1.0), "mmol": ("amount", 1e-3),
    "L": ("volume", 1.0), "mL": ("volume", 1e-3), "µL": ("volume", 1e-6),
    "uL": ("volume", 1e-6),
    "V": ("voltage", 1.0), "mV": ("voltage", 1e-3), "kV": ("voltage", 1e3),
    "A": ("current", 1.0), "mA": ("current", 1e-3),
    "W": ("power", 1.0), "kW": ("power", 1e3),
    "J": ("energy", 1.0), "kJ": ("energy", 1e3), "eV": ("energy", 1.0),
    "dB": ("level", 1.0), "rpm": ("speed", 1.0),
    "°C": ("temperature", 1.0), "K": ("temperature", 1.0),
}

CN_TAIL_STRIP = ("达到了", "达到", "约为", "为约", "为", "是", "达", "约", "的")
CN_TOKEN = re.compile(r"[\u4e00-\u9fff]{2,12}")
EN_TOKEN = re.compile(r"[A-Za-z][A-Za-z\-]{2,}")
STOPWORDS_EN = {"the", "and", "for", "with", "was", "were", "are", "from",
                "than", "over", "under", "about", "approximately", "value"}


def norm_keyword(token):
    if not token:
        return ""
    t = token.strip().lower()
    changed = True
    while changed and t:
        changed = False
        for suf in CN_TAIL_STRIP:
            if t.endswith(suf) and len(t) > len(suf) + 1:
                t = t[: -len(suf)]
                changed = True
    return t


def context_keyword(text, match_start):
    """取匹配点之前 24 字符内最近的名词性关键词。"""
    back = text[max(0, match_start - 24):match_start]
    cn = CN_TOKEN.findall(back)
    if cn:
        return norm_keyword(cn[-1])
    en = [w for w in EN_TOKEN.findall(back) if w.lower() not in STOPWORDS_EN]
    if en:
        return norm_keyword(en[-1])
    return ""


def decimals_of(raw):
    return len(raw.split(".")[1]) if "." in raw else 0


def extract_mentions(text, sections, source_name):
    mentions = []
    # 全文行号 → 所属小节的快速定位
    line_section = {}
    for name, _start, lines in sections:
        for ln, _lt in lines:
            line_section[ln] = name
    all_lines = text.splitlines()
    for kind, pat, _ in PATTERNS:
        for m in pat.finditer(text):
            line_no = text.count("\n", 0, m.start()) + 1
            section = line_section.get(line_no, "正文(未分节)")
            line_text = all_lines[line_no - 1].strip() if line_no <= len(all_lines) else ""
            quote = line_text[:160]
            if kind == "sample_size":
                raw_val, unit, keyword = m.group(1), "count", "n"
            elif kind == "pvalue":
                raw_val, unit, keyword = m.group(2), "p", "p"
            elif kind == "pm":
                raw_val, unit = m.group(1), m.group(3) or ""
                keyword = context_keyword(text, m.start())
            elif kind == "percent":
                raw_val, unit = m.group(1), "%"
                keyword = context_keyword(text, m.start())
            elif kind == "unit":
                raw_val, unit = m.group(1), m.group(2)
                keyword = context_keyword(text, m.start())
            elif kind == "fold":
                raw_val, unit = m.group(1), "x"
                keyword = context_keyword(text, m.start())
            elif kind == "rate_frac":
                raw_val, unit = m.group(2), "frac"
                keyword = norm_keyword(m.group(1))
            else:  # pragma: no cover
                continue
            try:
                value = float(raw_val)
            except ValueError:
                continue
            if not keyword:
                continue
            fam, factor = UNIT_FAMILY.get(unit, (unit, 1.0))
            if kind == "percent":
                fam, factor = "%", 1.0
            if kind == "rate_frac":
                fam, factor = "%", 100.0  # 0.918 → 91.8 与 % 可比
            mentions.append({
                "kind": kind, "keyword": keyword, "family": fam,
                "value": value, "value_norm": value * factor,
                "raw": m.group(0).strip(), "raw_value": raw_val,
                "decimals": decimals_of(raw_val),
                "section": section, "line": line_no,
                "source": source_name, "quote": quote,
            })
    return mentions

# ---------------- 一致性比对 ----------------

def rounding_consistent(a, da, b, db):
    """两值在较粗精度下舍入一致 → 视为一致（舍入容差）。"""
    d = min(da, db)
    return round(a, d) == round(b, d)


def compare_mentions(mentions):
    groups = {}
    for mt in mentions:
        if mt["kind"] in ("sample_size", "pvalue"):
            groups.setdefault((mt["kind"], mt["family"]), []).append(mt)
    # 常规量：同单位族内按"关键词互为后缀（短者≥2字符）"做并查集聚簇，
    # 使「准确率」「模型准确率」「模型最终准确率」归为同一物理量。
    byfam = {}
    for mt in mentions:
        if mt["kind"] not in ("sample_size", "pvalue"):
            byfam.setdefault(mt["family"], []).append(mt)
    for fam, items in byfam.items():
        kws = sorted({m["keyword"] for m in items}, key=len)
        parent = {k: k for k in kws}

        def find(k):
            while parent[k] != k:
                parent[k] = parent[parent[k]]
                k = parent[k]
            return k
        for i in range(len(kws)):
            for j in range(i + 1, len(kws)):
                short, long_ = kws[i], kws[j]
                if len(short) >= 2 and long_.endswith(short):
                    parent[find(long_)] = find(short)
        for mt in items:
            groups.setdefault((find(mt["keyword"]), fam), []).append(mt)
    findings = []
    for key, items in sorted(groups.items()):
        # 去重后的不同归一化取值
        distinct = {}
        for mt in items:
            sig = round(mt["value_norm"], 9)
            distinct.setdefault(sig, []).append(mt)
        sigs = sorted(distinct)
        bad_pairs = []
        for i in range(len(sigs)):
            for j in range(i + 1, len(sigs)):
                a, b = distinct[sigs[i]][0], distinct[sigs[j]][0]
                if not rounding_consistent(a["value_norm"], a["decimals"],
                                           b["value_norm"], b["decimals"]):
                    bad_pairs.append((sigs[i], sigs[j]))
        if not bad_pairs:
            continue
        locs = []
        for sig in sigs:
            for mt in distinct[sig]:
                locs.append({
                    "value": mt["value"], "raw": mt["raw"],
                    "section": mt["section"], "line": mt["line"],
                    "source": mt["source"], "quote": mt["quote"],
                })
        display = {"sample_size": "样本量 n", "pvalue": "p 值"}.get(key[0], key[0])
        findings.append({
            "type": "numeric_inconsistency",
            "facet": "事实核验",
            "severity": "major",
            "quantity": "%s (%s)" % (display, key[1]),
            "distinct_values": [distinct[s][0]["raw"] for s in sigs],
            "locations": locs,
            "evidence": "同一量「%s」在多处出现不一致取值：%s" % (
                display, " vs ".join(sorted({distinct[s][0]["raw"] for s in sigs}))),
            "status": "open",
        })
    findings.sort(key=lambda f: (f["quantity"], f["distinct_values"]))
    for i, f in enumerate(findings, 1):
        f["id"] = "NUM-%03d" % i
    return findings

# ---------------- 保底 result.json ----------------

def load_contract(input_dir):
    path = os.path.join(input_dir, "case.json")
    case_id, contract, note = "unknown_case", list(DEFAULT_CONTRACT), None
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            data = json.load(f)
        case_id = data.get("case_id") or case_id
        oc = data.get("output_contract")
        if isinstance(oc, dict):
            contract = list(oc.keys())
        elif isinstance(oc, list) and all(isinstance(x, str) for x in oc):
            contract = list(oc)
        else:
            note = "output_contract 缺失或格式未知，回退默认字段集"
    except FileNotFoundError:
        note = "case.json 缺失，使用默认 case_id 与默认字段集"
    except Exception as e:  # noqa: BLE001
        note = "case.json 解析失败(%s)，回退默认字段集" % e
    return case_id, contract, note


def bootstrap_result(input_dir, output_dir):
    """第一次脚本调用即产出保底 partial result.json（若已存在则不覆盖）。"""
    os.makedirs(output_dir, exist_ok=True)
    target = os.path.join(output_dir, "result.json")
    if os.path.exists(target):
        return False
    case_id, contract, note = load_contract(input_dir)
    uncertainty = ["bootstrap: 仅写入保底 partial 结果，深查尚未运行"]
    if note:
        uncertainty.append(note)
    result = {}
    for field in contract:
        result[field] = None
    result["case_id"] = case_id
    if "status" in result:
        result["status"] = "partial"
    if "findings" in result:
        result["findings"] = []
    if "sources" in result:
        result["sources"] = []
    if "uncertainty" in result:
        result["uncertainty"] = uncertainty
    if "change_log" in result:
        result["change_log"] = [{"seq": 1, "action": "bootstrap",
                                 "detail": "numeric_scan 保底写入"}]
    if "review_report" in result:
        result["review_report"] = None
    result["null_reasons"] = {"review_report": "报告尚未生成（bootstrap 阶段）"}
    fd, tmp = tempfile.mkstemp(dir=output_dir, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    os.replace(tmp, target)
    return True

# ---------------- 主流程 ----------------

def render_md(report):
    out = ["# 数值一致性扫描报告", "",
           "- 材料数: %d" % len(report["materials"]),
           "- 数值提及数: %d" % report["mention_count"],
           "- 候选不一致: %d" % len(report["findings"]), ""]
    for f in report["findings"]:
        out.append("## %s %s" % (f["id"], f["quantity"]))
        out.append("- 证据: %s" % f["evidence"])
        for loc in f["locations"]:
            out.append("  - `%s` @ %s 第%d行: %s" % (
                loc["raw"], loc["section"], loc["line"], loc["quote"]))
        out.append("")
    if report["warnings"]:
        out.append("## 警告")
        out.extend("- %s" % w for w in report["warnings"])
    return "\n".join(out) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="跨位置数值一致性确定性扫描（摘要/正文/结论/图表标题比对）")
    ap.add_argument("--input", default="/input", help="输入目录（含 case.json 与材料）")
    ap.add_argument("--work", default="/app/work", help="工作目录（输出 numeric_report.*）")
    ap.add_argument("--output", default="/app/output",
                    help="成果目录（必要时写保底 result.json）")
    args = ap.parse_args(argv)

    if not os.path.isdir(args.input):
        print("错误: 输入目录不存在: %s" % args.input, file=sys.stderr)
        return 2
    os.makedirs(args.work, exist_ok=True)

    booted = bootstrap_result(args.input, args.output)

    materials, all_mentions, warnings = [], [], []
    for fn in sorted(os.listdir(args.input)):
        path = os.path.join(args.input, fn)
        if not os.path.isfile(path) or fn in SKIP_FILES:
            continue
        ext = os.path.splitext(fn)[1].lower()
        if ext not in TEXT_EXT and ext not in (".pdf", ".docx"):
            continue
        text, note = extract_material(path)
        entry = {"file": fn, "sha256": sha256_of(path),
                 "chars": len(text), "extract_status": "ok" if note is None else note}
        materials.append(entry)
        if note:
            warnings.append("%s: %s" % (fn, note))
            continue
        sections = split_sections(text)
        all_mentions.extend(extract_mentions(text, sections, fn))

    findings = compare_mentions(all_mentions)
    report = {
        "tool": "numeric_scan", "version": VERSION,
        "bootstrap_result_written": booted,
        "materials": materials,
        "mention_count": len(all_mentions),
        "findings": findings,
        "warnings": warnings,
    }
    rj = os.path.join(args.work, "numeric_report.json")
    fd, tmp = tempfile.mkstemp(dir=args.work, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    os.replace(tmp, rj)
    with open(os.path.join(args.work, "numeric_report.md"), "w",
              encoding="utf-8") as f:
        f.write(render_md(report))
    print("numeric_scan 完成: 材料 %d 份, 提及 %d 处, 候选不一致 %d 条%s" % (
        len(materials), len(all_mentions), len(findings),
        "（已写保底 result.json）" if booted else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
