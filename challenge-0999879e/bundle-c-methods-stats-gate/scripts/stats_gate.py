#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""stats_gate.py — 统计报告要素存在性矩阵扫描器。

职责：
1. 抽取 /input 下的稿件文本（PDF 经 pdftotext，DOCX 经 zipfile 解包，
   失败如实记录 extract_error，绝不编造内容）；
2. 按小节切分（Markdown 标题 / 中英文章节名）；
3. 扫描统计报告要素的存在性模式（样本量、检验名称、p 值、CI、效应量、
   多重比较校正、随机化、盲法、对照、重复、剔除、软件、误差棒等）；
4. 输出 work/stats_matrix.json + work/stats_matrix.md；
5. 作为流程第一步，同步写出保底 partial result.json（诚实门 + 原子写）。

只用 Python 3 标准库。
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

DEFAULT_CONTRACT = ["case_id", "status", "review_report", "findings",
                    "sources", "uncertainty", "change_log"]

METADATA_FILES = {"case.json", "task.md"}

# ---------------------------------------------------------------- 要素模式
ELEMENTS = {
    "sample_size": {
        "name": "样本量声明",
        "patterns": [r"\bn\s*=\s*\d+", r"样本量", r"sample\s*size", r"每组\s*n?\s*[=为]?\s*\d+"],
    },
    "test_name": {
        "name": "检验名称",
        "patterns": [r"t\s*检验", r"t-test", r"student'?s?\s*t",
                     r"ANOVA", r"方差分析", r"Mann-Whitney", r"Wilcoxon",
                     r"Kruskal", r"卡方", r"chi-?square", r"Fisher",
                     r"logistic", r"线性回归", r"Cox", r"秩和"],
    },
    "p_value": {
        "name": "p 值报告",
        "patterns": [r"\bp\s*[<≤=＞≥>]\s*0?\.\d+", r"\bp\s*值", r"\bp<0?\.05"],
    },
    "confidence_interval": {
        "name": "置信区间",
        "patterns": [r"95%\s*CI", r"置信区间", r"confidence\s*interval", r"\bCI\s*[=：:]"],
    },
    "effect_size": {
        "name": "效应量",
        "patterns": [r"effect\s*size", r"Cohen'?s\s*d", r"效应量",
                     r"odds\s*ratio", r"\bOR\s*[=值]", r"η\s*2", r"eta\s*squared", r"hedges"],
    },
    "multiplicity": {
        "name": "多重比较校正",
        "patterns": [r"Bonferroni", r"FDR", r"false\s*discovery",
                     r"多重比较", r"multiple\s*comparison", r"校正", r"adjust"],
    },
    "randomization": {
        "name": "随机化",
        "patterns": [r"随机", r"randomiz", r"randomis"],
    },
    "blinding": {
        "name": "盲法",
        "patterns": [r"盲", r"blind", r"单盲", r"双盲", r"三盲"],
    },
    "control_group": {
        "name": "对照组",
        "patterns": [r"对照", r"control\s*group", r"空白组", r"溶剂对照", r"vehicle",
                     r"阴性对照", r"阳性对照"],
    },
    "replication": {
        "name": "重复次数",
        "patterns": [r"生物学重复", r"技术重复", r"technical\s*replicat",
                     r"三次独立", r"独立重复", r"independent\s*experiment",
                     r"重复\s*3\s*次", r"重复三次", r"n\s*=\s*3\s*次"],
    },
    "exclusion_rule": {
        "name": "数据剔除规则",
        "patterns": [r"剔除", r"排除标准", r"exclud", r"outlier", r"离群"],
    },
    "software": {
        "name": "统计软件版本",
        "patterns": [r"SPSS", r"GraphPad", r"Prism", r"Stata", r"R\s*语言",
                     r"R\s*版本", r"\bversion\s*\d+\.\d", r"软件版本",
                     r"RStudio", r"SAS"],
    },
    "error_bars": {
        "name": "误差棒定义",
        "patterns": [r"误差棒", r"error\s*bar", r"mean\s*±\s*SD", r"mean\s*±\s*SEM",
                     r"平均值\s*±", r"均数\s*±", r"以\s*mean\s*±"],
    },
}

SECTION_HEADER_RE = re.compile(
    r"^(#{1,6}\s+\S[^\n]{0,60}|"
    r"摘要|关键词|Abstract|Keywords|引言|Introduction|"
    r"材料与方法|材料方法|研究方法|方法|Methods|Methodology|"
    r"统计学方法|统计分析|Statistical\s*analysis|"
    r"结果|Results|Result|"
    r"讨论|Discussion|"
    r"结论|Conclusion|Conclusions|"
    r"参考文献|References|致谢|Acknowledg|"
    r"伦理|Ethic|数据可得性|Data\s*availability|利益冲突|Conflict)\s*$"
)


# ---------------------------------------------------------------- 工具函数
def read_text_file(path):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def extract_pdf(path, work_dir):
    """调用 pdftotext 抽取 PDF 文本；不可用或失败时返回 (None, error)。"""
    exe = shutil.which("pdftotext")
    if not exe:
        return None, "pdftotext not found (shutil.which)"
    try:
        out = subprocess.run([exe, "-layout", path, "-"],
                             capture_output=True, timeout=120)
        if out.returncode != 0:
            return None, "pdftotext exit %d: %s" % (
                out.returncode, out.stderr.decode("utf-8", "replace")[:200])
        return out.stdout.decode("utf-8", "replace"), None
    except Exception as e:  # noqa: BLE001 — 如实记录任何抽取异常
        return None, "pdftotext exception: %r" % e


def extract_docx(path):
    """用 zipfile 抽取 DOCX 正文（stdlib），失败如实记录。"""
    try:
        with zipfile.ZipFile(path) as z:
            xml = z.read("word/document.xml").decode("utf-8", "replace")
        xml = re.sub(r"</w:p>", "\n", xml)
        return re.sub(r"<[^>]+>", "", xml), None
    except Exception as e:  # noqa: BLE001
        return None, "docx extract exception: %r" % e


def extract_inputs(input_dir, work_dir):
    """抽取 input_dir 下全部稿件文本，返回 (docs, errors)。

    docs: [{"file","sha256","text"}]；errors: [{"file","error"}]
    """
    docs, errors = [], []
    if not os.path.isdir(input_dir):
        return docs, [{"file": input_dir, "error": "input dir not found"}]
    for name in sorted(os.listdir(input_dir)):
        path = os.path.join(input_dir, name)
        if not os.path.isfile(path) or name in METADATA_FILES:
            continue
        ext = os.path.splitext(name)[1].lower()
        sha = hashlib.sha256()
        with open(path, "rb") as f:
            sha.update(f.read())
        digest = sha.hexdigest()
        if ext == ".pdf":
            text, err = extract_pdf(path, work_dir)
        elif ext == ".docx":
            text, err = extract_docx(path)
        elif ext in (".md", ".txt", ".tex", ""):
            text, err = read_text_file(path), None
        else:
            text, err = None, "unsupported extension %r" % ext
        if err or text is None:
            errors.append({"file": name, "sha256": digest, "extract_error": err or "empty"})
            continue
        docs.append({"file": name, "sha256": digest, "text": text})
    return docs, errors


def split_sections(text):
    """把文本按小节标题切分为 [{"title","start","text"}]。

    找不到任何标题时退化为单小节 "全文"。
    """
    sections = []
    cur_title, cur_start, cur_lines = None, 0, []
    offset = 0
    found_header = False
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if SECTION_HEADER_RE.match(stripped) and len(stripped) <= 64:
            found_header = True
            if cur_title is not None:
                sections.append({"title": cur_title, "start": cur_start,
                                 "text": "".join(cur_lines)})
            cur_title = re.sub(r"^#{1,6}\s*", "", stripped)
            cur_start = offset + len(line)  # 正文从标题行之后开始
            cur_lines = []
        else:
            cur_lines.append(line)
        offset += len(line)
    if cur_title is not None:
        sections.append({"title": cur_title, "start": cur_start,
                         "text": "".join(cur_lines)})
    if not found_header:
        return [{"title": "全文", "start": 0, "text": text}]
    if sections and sections[0]["text"].strip() == "" and sections[0]["start"] == 0:
        pass  # 首个标题位于文首，正常
    # 标题之前的正文（如摘要前无标题的段落）并入 "前言部分"
    if sections and sections[0]["start"] > 0:
        sections.insert(0, {"title": "（文首无标题部分）", "start": 0,
                            "text": text[:sections[0]["start"]]})
    return sections


_SENT_END = "。；;！!？?"


def sentence_around(text, idx, limit=220):
    """取 idx 附近的一句话（用于原文定位引证）。

    单个换行视为软换行（中文稿常见），空行才算断句边界。"""
    start = idx
    while start > 0:
        c = text[start - 1]
        if c in _SENT_END:
            break
        if c == "\n" and (start - 2 < 0 or text[start - 2] == "\n"):
            break
        start -= 1
    end = idx
    while end < len(text):
        c = text[end]
        if c in _SENT_END:
            break
        if c == "\n" and (end + 1 >= len(text) or text[end + 1] == "\n"):
            break
        end += 1
    sent = text[start:end].strip()
    if len(sent) > limit:
        sent = sent[:limit] + "…"
    return sent


def scan_elements(docs):
    """对每个要素在每个文件每个小节扫描存在性。"""
    result = {}
    for key, spec in ELEMENTS.items():
        found = []
        for doc in docs:
            for sec in doc["sections"]:
                for pat in spec["patterns"]:
                    m = re.search(pat, sec["text"], re.IGNORECASE)
                    if m:
                        abs_off = sec["start"] + m.start()
                        found.append({
                            "file": doc["file"],
                            "section": sec["title"],
                            "offset": abs_off,
                            "quote": sentence_around(doc["text"], abs_off),
                        })
                        break  # 每小节记录首条命中即可
        result[key] = {
            "name": spec["name"],
            "status": "found" if found else "absent",
            "found_at": found,
        }
    return result


def render_matrix_md(matrix):
    lines = ["# 统计报告要素矩阵（stats_matrix）", "",
             "| 要素 | 状态 | 出现位置（小节 / 原文摘录） |", "|---|---|---|"]
    for key, item in matrix.items():
        if item["status"] == "found":
            locs = "；".join("%s《%s》: %s" % (f["file"], f["section"], f["quote"][:60])
                             for f in item["found_at"][:3])
            lines.append("| %s | found | %s |" % (item["name"], locs.replace("|", "/")))
        else:
            lines.append("| %s | absent | — |" % item["name"])
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------- 契约回退
def resolve_contract(case):
    oc = case.get("output_contract") if isinstance(case, dict) else None
    note = None
    if isinstance(oc, dict):
        fields = list(oc.keys())
    elif isinstance(oc, list) and all(isinstance(x, str) for x in oc) and oc:
        fields = list(oc)
    else:
        fields = list(DEFAULT_CONTRACT)
        if oc is None:
            note = "case.json 缺少 output_contract 或 schema 未识别，已回退默认字段集"
        else:
            note = "output_contract 类型未识别(%s)，已回退默认字段集" % type(oc).__name__
    if "case_id" not in fields:
        fields = ["case_id"] + fields
    return fields, note


def atomic_write_json(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def load_case(input_dir):
    path = os.path.join(input_dir, "case.json")
    if not os.path.isfile(path):
        return {"case_id": "unknown"}, ["case.json 不存在，case_id 记为 unknown"]
    try:
        return json.loads(read_text_file(path)), []
    except Exception as e:  # noqa: BLE001
        return {"case_id": "unknown"}, ["case.json 解析失败 %r，case_id 记为 unknown" % e]


def write_partial_result(input_dir, output_dir, extraction_errors):
    """保底 partial result.json：第一次脚本调用即产出，绝不空跑。"""
    case, case_notes = load_case(input_dir)
    fields, contract_note = resolve_contract(case)
    uncertainty = list(case_notes) + [
        "stats_gate 阶段产物：仅为要素存在性扫描，尚未完成清单门禁判定"] + [
        "抽取失败文件: %s (%s)" % (e["file"], e["extract_error"])
        for e in extraction_errors]
    if contract_note:
        uncertainty.append(contract_note)
    payload = {
        "case_id": case.get("case_id", "unknown"),
        "status": "partial",
        "review_report": "partial：stats_gate 已完成文本抽取与要素矩阵扫描，"
                         "清单门禁判定待 gate_check / build_result 补全。",
        "findings": [],
        "sources": [],
        "uncertainty": uncertainty,
        "change_log": ["stats_gate.py: 抽取稿件 + 生成统计报告要素矩阵（partial 保底产物）"],
    }
    for f in fields:
        payload.setdefault(f, None if f not in payload else payload[f])
    atomic_write_json(os.path.join(output_dir, "result.json"), payload)
    return payload["case_id"]


# ---------------------------------------------------------------- 主流程
def main(argv=None):
    ap = argparse.ArgumentParser(
        description="统计报告要素存在性矩阵扫描器（bundle-c-methods-stats-gate）")
    ap.add_argument("--input-dir", default="/input", help="输入目录（默认 /input）")
    ap.add_argument("--work-dir", default="/app/work", help="工作目录（默认 /app/work）")
    ap.add_argument("--output-dir", default="/app/output", help="输出目录（默认 /app/output）")
    args = ap.parse_args(argv)

    try:
        os.makedirs(args.work_dir, exist_ok=True)
        os.makedirs(args.output_dir, exist_ok=True)
    except OSError as e:
        print("无法创建工作/输出目录: %r" % e, file=sys.stderr)
        return 1

    docs, errors = extract_inputs(args.input_dir, args.work_dir)
    if not docs:
        print("警告：/input 下未抽取到任何稿件文本，矩阵将全部记为 unable_to_check",
              file=sys.stderr)

    full_docs = docs  # 扫描用同一份抽取结果，避免重复 IO
    for doc in full_docs:
        doc["sections"] = split_sections(doc["text"])
    matrix = scan_elements(full_docs) if full_docs else {
        k: {"name": v["name"], "status": "absent", "found_at": [],
            "note": "无稿件文本，无法扫描"}
        for k, v in ELEMENTS.items()}

    section_index = [{"file": d["file"],
                      "sections": [{"title": s["title"], "start": s["start"]}
                                   for s in d["sections"]]}
                     for d in full_docs]

    matrix_payload = {
        "generated_by": "stats_gate.py",
        "pdftotext_available": bool(shutil.which("pdftotext")),
        "extraction_errors": errors,
        "manuscripts": [{"file": d["file"], "sha256": d["sha256"],
                         "n_sections": len(d["sections"])} for d in full_docs],
        "sections": section_index,
        "elements": matrix,
    }

    matrix_path = os.path.join(args.work_dir, "stats_matrix.json")
    atomic_write_json(matrix_path, matrix_payload)

    md = render_matrix_md(matrix)
    md_path = os.path.join(args.work_dir, "stats_matrix.md")
    with open(md_path, "w", encoding="utf-8", errors="replace") as f:
        f.write(md)

    case_id = write_partial_result(args.input_dir, args.output_dir, errors)

    print("stats_matrix: %d 个要素，%d 个稿件文件，%d 个抽取错误" %
          (len(matrix), len(full_docs), len(errors)))
    for key, item in matrix.items():
        print("  %-22s %s" % (key, item["status"]))
    print("partial result.json 已写出（case_id=%s）" % case_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
