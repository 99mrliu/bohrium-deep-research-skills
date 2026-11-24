#!/usr/bin/env python3
"""doc_map.py — 结构制图第一步：文本抽取 + 标题层级解析 + 要素齐备性 + 句子级对齐表。

用法:
    python3 doc_map.py --input /input --work /app/work --output /app/output

产物:
    /app/output/result.json   保底 partial 结果（本脚本被调用即先落盘，诚实门）
    /app/work/manuscript.txt  抽取后的全文（utf-8, errors=replace）
    /app/work/doc_map.json    结构树 + 角色矩阵 + 摘要↔结论对齐表 + 引言问题↔结论配对

退出码: 0 成功；非 0 失败并打印原因到 stderr（保底 result.json 仍会尽量写出）。
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

DEFAULT_FIELDS = ["case_id", "status", "review_report", "findings", "sources",
                  "uncertainty", "change_log"]

TEXT_EXTS = [".md", ".txt", ".tex"]
ROLE_ORDER = ["abstract", "introduction", "methods", "results", "discussion",
              "conclusion", "references"]
ROLE_PATTERNS = {
    "abstract": [r"abstract", r"摘要"],
    "introduction": [r"introduction", r"引言", r"前言", r"研究背景", r"背景"],
    "methods": [r"methods?", r"materials?", r"方法", r"材料与方法", r"研究设计",
                r"实验设计", r"对象与方法", r"资料与方法"],
    "results": [r"results?", r"结果", r"研究发现"],
    "discussion": [r"discussion", r"讨论"],
    "conclusion": [r"conclusions?", r"concluding", r"结论", r"总结", r"小结"],
    "references": [r"references?", r"bibliography", r"参考文献", r"文献"],
}
# 讨论节的合理推测措辞，供下游防误报参考（详见 references/argument_rubric.md）
HEDGING_TERMS = ["提示", "可能", "或许", "推测", "suggest", "may", "might", "could"]

RE_MD_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
RE_NUM_HEADING = re.compile(r"^(\d{1,2}(?:\.\d{1,2}){0,3})[\.、]?\s+(\S.{0,38})$")
RE_CN_HEADING = re.compile(r"^([一二三四五六七八九十]{1,3})、\s*(\S.{0,38})$")
RE_TEX_HEADING = re.compile(r"^\\(section|subsection|subsubsection)\*?\{(.+)\}\s*$")
RE_SENT_SPLIT = re.compile(r"(?<=[。！？!?])\s*|(?<=\.)\s+|[；;]\s*|\n+")
RE_PREFIX_NUM = re.compile(r"^(\d+(?:\.\d+)*[\.、]?|[一二三四五六七八九十]{1,3}、)\s*")


def eprint(msg):
    sys.stderr.write("doc_map.py: %s\n" % msg)


def read_json_tolerant(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return json.load(f)
    except Exception:
        return {}


def resolve_contract(case):
    """output_contract 可能是字段名列表或 dict；找不到回退默认字段集。"""
    note = None
    contract = case.get("output_contract")
    if isinstance(contract, list) and all(isinstance(x, str) for x in contract):
        fields = list(contract)
    elif isinstance(contract, dict):
        fields = list(contract.keys())
    else:
        fields = list(DEFAULT_FIELDS)
        note = ("case.json 未提供可识别的 output_contract（既非字段名列表也非 dict），"
                "已回退默认字段集 %s" % DEFAULT_FIELDS)
    return fields, note


def atomic_write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def write_fallback_result(output_dir, case_id, contract_fields, uncertainty):
    """保底 partial result.json：第一次脚本调用即产出，之后由 build_result.py 覆盖。"""
    result = {k: None for k in contract_fields}
    result.update({
        "case_id": case_id,
        "status": "partial",
        "review_report": None,
        "findings": [],
        "sources": [],
        "uncertainty": uncertainty,
        "change_log": ["doc_map.py 写入保底 partial result.json；结构制图/论证链审查尚未完成"],
    })
    atomic_write_json(os.path.join(output_dir, "result.json"), result)


def pick_manuscript(input_dir):
    """在 /input 下挑选稿件文件：优先 manuscript/paper 命名，其次最大文本/PDF/DOCX。"""
    cands = []
    for name in sorted(os.listdir(input_dir)):
        low = name.lower()
        if low in ("case.json", "task.md"):
            continue
        ext = os.path.splitext(low)[1]
        if ext in TEXT_EXTS + [".pdf", ".docx"]:
            path = os.path.join(input_dir, name)
            if os.path.isfile(path):
                cands.append(path)
    if not cands:
        return None
    preferred = [p for p in cands if re.search(r"manuscript|paper|稿件|正文",
                                               os.path.basename(p).lower())]
    pool = preferred or cands
    return max(pool, key=os.path.getsize)


def extract_text(path):
    """返回 (text, method, error)。PDF 用 pdftotext（无则如实记录）；DOCX 用 stdlib zipfile 尽力抽取。"""
    ext = os.path.splitext(path)[1].lower()
    if ext in TEXT_EXTS:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read(), "direct-read(%s)" % ext, None
    if ext == ".pdf":
        tool = shutil.which("pdftotext")
        if not tool:
            return None, "pdftotext", ("未找到 pdftotext，无法抽取 PDF 文本；"
                                       "请安装 poppler 或提供文本版稿件")
        try:
            out = subprocess.run([tool, "-layout", path, "-"],
                                 capture_output=True, timeout=120)
            if out.returncode != 0:
                return None, "pdftotext", "pdftotext 退出码 %d: %s" % (
                    out.returncode, out.stderr.decode("utf-8", "replace")[:300])
            return out.stdout.decode("utf-8", "replace"), "pdftotext -layout", None
        except Exception as exc:  # noqa: BLE001
            return None, "pdftotext", "pdftotext 调用异常: %s" % exc
    if ext == ".docx":
        import zipfile
        try:
            with zipfile.ZipFile(path) as zf:
                xml = zf.read("word/document.xml").decode("utf-8", "replace")
            xml = re.sub(r"<w:p[ >/]", "\n<w:p ", xml)
            xml = re.sub(r"<w:br[^>]*/>", "\n", xml)
            text = re.sub(r"<[^>]+>", "", xml)
            import html
            return html.unescape(text), "stdlib-zipfile(docx)", None
        except Exception as exc:  # noqa: BLE001
            return None, "stdlib-zipfile(docx)", "DOCX 抽取失败: %s" % exc
    return None, "unknown", "不支持的文件类型: %s" % ext


def clean_title(title):
    return RE_PREFIX_NUM.sub("", title).strip()


def match_role(title):
    t = clean_title(title).lower()
    t = re.sub(r"[\s:：\-—()（）]", "", t)
    if not t:
        return None
    for role in ROLE_ORDER:
        for pat in ROLE_PATTERNS[role]:
            if re.search(pat, t):
                return role
    return None


def parse_headings(lines):
    r"""解析标题层级：markdown #、数字编号 1./1.1、中文 一、、TeX \section 均尝试。"""
    headings = []
    for idx, raw in enumerate(lines, start=1):
        line = raw.rstrip()
        if not line.strip():
            continue
        m = RE_MD_HEADING.match(line)
        if m:
            headings.append({"line": idx, "level": len(m.group(1)),
                             "title": m.group(2).strip(), "style": "markdown"})
            continue
        m = RE_TEX_HEADING.match(line)
        if m:
            lvl = {"section": 1, "subsection": 2, "subsubsection": 3}[m.group(1)]
            headings.append({"line": idx, "level": lvl,
                             "title": m.group(2).strip(), "style": "tex"})
            continue
        # 编号式标题需保守：短行、无句末标点，避免把正文数字开头误判为标题
        if len(line) <= 42 and not re.search(r"[。；，,;!?！？]$", line):
            m = RE_NUM_HEADING.match(line)
            if m and not line.lstrip().startswith("#"):
                depth = m.group(1).count(".") + 1
                title = m.group(2).strip()
                # 编号标题需像标题：含角色关键词，或编号本身是层级形式（含点）
                if match_role(m.group(1) + " " + title) or "." in m.group(1) \
                        or re.match(r"^\d{1,2}[\.、]\s*\S", line):
                    headings.append({"line": idx, "level": min(depth + 1, 6),
                                     "title": ("%s %s" % (m.group(1), title)).strip(),
                                     "style": "numbered"})
                continue
            m = RE_CN_HEADING.match(line)
            if m:
                headings.append({"line": idx, "level": 2,
                                 "title": ("%s、%s" % (m.group(1), m.group(2))).strip(),
                                 "style": "chinese-numbered"})
    for h in headings:
        h["role"] = match_role(h["title"])
    return headings


def build_sections(lines, headings):
    """每个标题的正文区间 = 到下一个 level <= 自身的标题为止。"""
    sections = []
    for i, h in enumerate(headings):
        end = len(lines) + 1
        for h2 in headings[i + 1:]:
            if h2["level"] <= h["level"]:
                end = h2["line"]
                break
        body = "\n".join(lines[h["line"]:end - 1]).strip()
        sections.append({"line": h["line"], "end_line": end - 1,
                         "level": h["level"], "title": h["title"],
                         "role": h["role"], "text": body})
    return sections


def build_tree(sections):
    root = {"title": "(document)", "level": 0, "children": []}
    stack = [root]
    for s in sections:
        node = {"title": s["title"], "level": s["level"], "line": s["line"],
                "role": s["role"], "children": []}
        while len(stack) > 1 and stack[-1]["level"] >= s["level"]:
            stack.pop()
        stack[-1]["children"].append(node)
        stack.append(node)
    return root["children"]


def split_sentences(text):
    parts = RE_SENT_SPLIT.split(text)
    return [p.strip() for p in parts if p and len(p.strip()) >= 4]


def char_bigrams(s):
    cleaned = re.sub(r"[^\w一-鿿]", "", s.lower())
    grams = {cleaned[i:i + 2] for i in range(len(cleaned) - 1)}
    if len(cleaned) == 1:
        grams.add(cleaned)
    return grams


def overlap(a, b):
    ga, gb = char_bigrams(a), char_bigrams(b)
    if not ga or not gb:
        return 0.0
    return len(ga & gb) / float(min(len(ga), len(gb)))


def question_coverage(question, answer):
    """问题被回答的覆盖度 = 问题的字符二元组在答案句中的命中比例。

    阈值 0.4：结论句至少覆盖问题 40% 的语义片段才算"疑似已回应"，
    低于阈值进入"疑似未回应"候选，由 Agent 人工核对（防误报见 argument_rubric.md）。
    """
    gq, ga = char_bigrams(question), char_bigrams(answer)
    if not gq or not ga:
        return 0.0
    return len(gq & ga) / float(len(gq))


def role_sentences(sections, role):
    """该角色（取第一个命中的标题区间）的句子列表，带定位。"""
    for s in sections:
        if s["role"] == role:
            sents = split_sentences(s["text"])
            return [{"text": t, "locator": "%s#s%d" % (role, i + 1),
                     "section_line": s["line"]} for i, t in enumerate(sents)]
    return []


def question_core(text):
    """提取问句核心：去掉'本文旨在回答两个问题：'类前导与（1）类枚举标记，
    避免前导稀释关键词覆盖度。"""
    core = text.strip()
    # 去掉最后一个冒号/逗号之前的前导（保留真正疑问子句）
    m = re.search(r"[：:，,][^：:，,]*[？?]", core)
    if m and m.start() < len(core) // 2:
        core = core[m.start() + 1:]
    core = re.sub(r"^[（(]\s*\d+\s*[）)]\s*", "", core)
    return core.strip() or text.strip()


def find_questions(intro_sents):
    qs = []
    for s in intro_sents:
        if "？" in s["text"] or "?" in s["text"]:
            s = dict(s)
            s["core"] = question_core(s["text"])
            qs.append(s)
    return qs


def main():
    ap = argparse.ArgumentParser(description="结构制图：抽取稿件并生成 doc_map.json")
    ap.add_argument("--input", required=True, help="输入目录（含 case.json/task.md/稿件）")
    ap.add_argument("--work", required=True, help="工作目录（如 /app/work）")
    ap.add_argument("--output", required=True, help="输出目录（如 /app/output）")
    ap.add_argument("--manuscript", default=None, help="显式指定稿件文件（可选）")
    args = ap.parse_args()

    os.makedirs(args.work, exist_ok=True)
    os.makedirs(args.output, exist_ok=True)

    case = read_json_tolerant(os.path.join(args.input, "case.json"))
    case_id = case.get("case_id", "unknown-case")
    contract, contract_note = resolve_contract(case)
    uncertainty = []
    if contract_note:
        uncertainty.append(contract_note)

    # 诚实门 / 预算保护：先落盘保底 partial result.json
    try:
        write_fallback_result(args.output, case_id, contract,
                              uncertainty + ["保底结果：doc_map.py 尚在执行或中途失败"])
    except Exception as exc:  # noqa: BLE001
        eprint("警告：保底 result.json 写入失败: %s" % exc)

    # 1. 定位并抽取稿件
    mpath = args.manuscript or pick_manuscript(args.input)
    if not mpath:
        eprint("失败：/input 下未找到稿件文件（md/txt/tex/pdf/docx）")
        write_fallback_result(args.output, case_id, contract,
                              uncertainty + ["未找到稿件文件，无法审查"])
        return 2
    sha = hashlib.sha256()
    with open(mpath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha.update(chunk)
    sha256 = sha.hexdigest()

    text, method, extract_error = extract_text(mpath)
    if extract_error:
        eprint("失败：%s" % extract_error)
        doc_map = {
            "case_id": case_id,
            "manuscript_file": os.path.abspath(mpath),
            "manuscript_sha256": sha256,
            "extract": {"method": method, "error": extract_error, "char_count": 0},
            "headings": [], "structure_tree": [], "role_matrix": {},
            "section_sentences": {},
            "abstract_conclusion_alignment": [], "intro_questions": [],
            "warnings": [extract_error],
        }
        atomic_write_json(os.path.join(args.work, "doc_map.json"), doc_map)
        write_fallback_result(args.output, case_id, contract,
                              uncertainty + ["文本抽取失败: %s" % extract_error])
        return 3
    if extract_error is None and not text.strip():
        eprint("失败：抽取结果为空文本")
        write_fallback_result(args.output, case_id, contract,
                              uncertainty + ["文本抽取结果为空"])
        return 3

    with open(os.path.join(args.work, "manuscript.txt"), "w",
              encoding="utf-8", errors="replace") as f:
        f.write(text)

    # 2. 标题层级与角色
    lines = text.splitlines()
    headings = parse_headings(lines)
    sections = build_sections(lines, headings)
    tree = build_tree(sections)

    # 只统计"顶层角色标题"：已位于某角色小节内的子标题（如"2.1 研究设计"在"2. 方法"下）
    # 视为内容子节，不参与齐备性计数，避免 ambiguous 误报。
    top_hits = {r: [] for r in ROLE_ORDER}
    stack = []  # (level, effective_role)
    for s in sections:
        while stack and stack[-1][0] >= s["level"]:
            stack.pop()
        ancestor_role = stack[-1][1] if stack else None
        if s["role"] and ancestor_role is None:
            top_hits[s["role"]].append(s)
        stack.append((s["level"], s["role"] or ancestor_role))

    role_matrix = {}
    for role in ROLE_ORDER:
        hits = top_hits[role]
        if len(hits) == 1:
            status = "present"
        elif len(hits) > 1:
            status = "ambiguous"
        else:
            status = "absent"
        role_matrix[role] = {
            "status": status,
            "headings": [{"title": h["title"], "line": h["line"]} for h in hits],
        }

    warnings = []
    if not headings:
        warnings.append("未解析出任何标题，结构树为空；可能为无标题纯文本稿件")
    for role, info in role_matrix.items():
        if info["status"] == "absent":
            warnings.append("标准小节缺失: %s" % role)
        elif info["status"] == "ambiguous":
            warnings.append("标准小节疑似重复（ambiguous）: %s" % role)

    # 3. 摘要↔结论句子级对齐表（按关键词重叠配对）
    abs_sents = role_sentences(sections, "abstract")
    con_sents = role_sentences(sections, "conclusion")
    intro_sents = role_sentences(sections, "introduction")
    res_sents = role_sentences(sections, "results")
    meth_sents = role_sentences(sections, "methods")
    disc_sents = role_sentences(sections, "discussion")

    alignment = []
    for cs in con_sents:
        best, best_score = None, 0.0
        for as_ in abs_sents:
            sc = overlap(cs["text"], as_["text"])
            if sc > best_score:
                best, best_score = as_, sc
        alignment.append({
            "conclusion_sentence": cs["text"],
            "conclusion_locator": cs["locator"],
            "best_abstract_sentence": best["text"] if best else None,
            "best_abstract_locator": best["locator"] if best else None,
            "overlap_score": round(best_score, 3),
        })

    # 4. 引言问题↔结论回答配对
    questions = []
    for q in find_questions(intro_sents):
        best, best_score = None, 0.0
        for cs in con_sents:
            sc = question_coverage(q["core"], cs["text"])
            if sc > best_score:
                best, best_score = cs, sc
        questions.append({
            "question": q["text"],
            "question_core": q["core"],
            "question_locator": q["locator"],
            "best_conclusion_sentence": best["text"] if best else None,
            "best_conclusion_locator": best["locator"] if best else None,
            "overlap_score": round(best_score, 3),
            "answered_candidate": best_score >= 0.4,
        })

    doc_map = {
        "case_id": case_id,
        "manuscript_file": os.path.abspath(mpath),
        "manuscript_sha256": sha256,
        "extract": {"method": method, "error": None, "char_count": len(text)},
        "output_contract_fields": contract,
        "headings": headings,
        "structure_tree": tree,
        "role_matrix": role_matrix,
        "section_sentences": {
            "abstract": abs_sents, "introduction": intro_sents,
            "methods": meth_sents, "results": res_sents,
            "discussion": disc_sents, "conclusion": con_sents,
        },
        "abstract_conclusion_alignment": alignment,
        "intro_questions": questions,
        "warnings": warnings,
    }
    atomic_write_json(os.path.join(args.work, "doc_map.json"), doc_map)
    print("doc_map.json 已生成: 标题 %d 个, 角色矩阵 %d 项, 引言问题 %d 个, "
          "结论句 %d 句 (sha256=%s...)" % (
              len(headings), len(role_matrix), len(questions),
              len(con_sents), sha256[:12]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
