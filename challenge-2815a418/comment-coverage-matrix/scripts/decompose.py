#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""decompose.py — reviewer-comments.md -> matrix.json 骨架。

按 R#/编号/段落把意见拆成块；块内按连接词与句子边界建议子要求拆分，
预填 type/severity/action 猜测与逐字 raw_text。
防漏条原则：骨架里子要求只多不少，由 Agent 后续合并，不得由本脚本合并。

用法:
  python3 decompose.py --comments reviewer-comments.md [--case case.json] --out matrix.json
"""
import argparse, json, re, sys, os
from datetime import datetime, timezone

# 意见块头：R1 / R1.2 / 意见1 / Comment 1 / Reviewer 1 第2条 / 1. / 1、/ 1) 等
BLOCK_RE = re.compile(
    r'^\s*#*\s*(?:'
    r'(?P<r>R\s*(?P<rn>\d+)(?:\s*[-–.]\s*\d+)?)'
    r'|意见\s*(?P<cn>\d+)'
    r'|(?:Comment|COMMENT|comment)\s*(?P<mn>\d+)'
    r'|(?P<num>\d+)\s*[\.、\)]\s'
    r')')
# 拆点：连接词（保留在新子要求开头）
CONN_RE = re.compile(
    r'(同时|并且|而且|另外|此外|再者|以及|also|moreover|furthermore|additionally|in addition|besides)',
    re.IGNORECASE)
SENT_RE = re.compile(r'([。！？!?；;])')

EVIDENCE_ACTIONS = {"补实验", "补数据", "补文献", "重做分析"}


def has_cjk(s):
    return any('一' <= ch <= '鿿' for ch in s)


def guess_type(text):
    rules = [
        ("伦理", ["伦理", "知情同意", "ethic", "consent", "IRB", "动物", "隐私"]),
        ("格式", ["格式", "排版", "字体", "行号", "模板", "format", "排版"]),
        ("数据", ["数据", "样本量", "数据集", "统计", "显著性", "p值", "p-value", "dataset", "sample size", "significance", "外部验证", "泛化"]),
        ("方法", ["方法", "模型", "算法", "实验设计", "参数", "超参", "预处理", "对照", "消融", "ablation", "baseline", "method", "model", "algorithm", "依据", "选择依据"]),
        ("写作", ["写作", "表述", "语言", "语法", "措辞", "可读性", "讨论", "结论部分", "摘要", "typo", "grammar", "clarity", "writing", "局限"]),
    ]
    low = text.lower()
    for t, kws in rules:
        if any(k.lower() in low for k in kws):
            return t
    return "其他"


def guess_action(text):
    low = text.lower()
    rules = [
        ("补实验", ["补实验", "补充实验", "增加实验", "实验验证", "额外实验", "additional experiment", "new experiment", "外部验证实验"]),
        ("补数据", ["补数据", "补充数据", "更多数据", "扩充数据", "additional data", "more data"]),
        ("补文献", ["引用", "文献", "参考文献", "cite", "citation", "reference"]),
        ("重做分析", ["重做分析", "重新分析", "重跑", "重新统计", "对比分析", "敏感性分析", "reanalysis", "re-run", "sensitivity"]),
        ("澄清解释", ["澄清", "解释", "说明", "为什么", "依据", "如何", "clarify", "explain", "why", "how"]),
    ]
    for a, kws in rules:
        if any(k.lower() in low for k in kws):
            return a
    return "修改文本"


def guess_severity(text, action):
    low = text.lower()
    if action in EVIDENCE_ACTIONS:
        return "major"
    if any(k in low for k in ["major", "必须", "严重", "根本", "缺乏", "致命"]):
        return "major"
    if any(k in low for k in ["minor", "typo", "建议", "可考虑", "optional"]):
        return "minor"
    return "minor"


def split_sentences(text):
    """按句末标点与连接词切分；连接词留在新片段开头。只拆不并。"""
    text = re.sub(r'\s+', ' ', text).strip()
    if not text:
        return []
    # 先按连接词切
    parts = CONN_RE.split(text)
    segs = []
    buf = ""
    for p in parts:
        if p is None:
            continue
        if CONN_RE.fullmatch(p):
            if buf.strip():
                segs.append(buf.strip())
            buf = p
        else:
            buf += p
    if buf.strip():
        segs.append(buf.strip())
    # 再按句末标点切（保留标点在前一段）
    out = []
    for seg in segs:
        pieces = SENT_RE.split(seg)
        cur = ""
        for pc in pieces:
            cur += pc
            if SENT_RE.fullmatch(pc or ""):
                if cur.strip():
                    out.append(cur.strip())
                cur = ""
        if cur.strip():
            out.append(cur.strip())
    # 极短碎片（<6 字符且非疑问句）挂回上一段，避免无意义碎片
    merged = []
    for s in out:
        if merged and len(s) < 6 and not s.endswith(('?', '？')):
            merged[-1] = merged[-1] + " " + s
        else:
            merged.append(s)
    return merged


def parse_blocks(text):
    lines = text.splitlines()
    blocks = []  # (comment_id, [lines])
    cur_id, cur = None, []
    for ln in lines:
        m = BLOCK_RE.match(ln)
        if m:
            if cur_id is not None:
                blocks.append((cur_id, cur))
            if m.group('rn'):
                cur_id = "R" + m.group('rn')
            elif m.group('cn'):
                cur_id = "R" + m.group('cn')
            elif m.group('mn'):
                cur_id = "R" + m.group('mn')
            else:
                cur_id = "R" + m.group('num')
            cur = [BLOCK_RE.sub('', ln, count=1).strip()]
        else:
            if cur_id is None:
                continue  # 忽略首个意见块之前的引言
            cur.append(ln)
    if cur_id is not None:
        blocks.append((cur_id, cur))
    if not blocks:
        # 无编号：每个非空段落算一条意见
        paras = [p.strip() for p in re.split(r'\n\s*\n', text) if p.strip()]
        blocks = [("R%d" % (i + 1), [p]) for i, p in enumerate(paras)]
    # 去重 comment_id（同名块合并内容）
    seen, merged = {}, []
    for cid, body in blocks:
        if cid in seen:
            seen[cid].extend(body)
        else:
            seen[cid] = body
            merged.append((cid, body))
    return merged


def build_matrix(comments_path, case_path=None):
    text = open(comments_path, encoding='utf-8').read()
    case_id = "UNKNOWN"
    if case_path and os.path.exists(case_path):
        try:
            cd = json.load(open(case_path, encoding='utf-8'))
            case_id = cd.get("case_id") or cd.get("caseId") or "UNKNOWN"
        except Exception:
            pass
    blocks = parse_blocks(text)
    comments = []
    for cid, body_lines in blocks:
        raw = "\n".join(body_lines).strip()
        raw = re.sub(r'\n{2,}', '\n', raw)
        segs = split_sentences(raw.replace("\n", " "))
        subs = []
        for i, seg in enumerate(segs, 1):
            action = guess_action(seg)
            subs.append({
                "sub_id": "%s.%d" % (cid, i),
                "raw_text": seg,
                "type": guess_type(seg),
                "severity": guess_severity(seg, action),
                "action": action,
                "relation": "并列",
                "depends_on": [],
                "decision": "待定",
                "decision_reason": "",
                "response_summary": "",
                "evidence": {"status": "", "source": "", "alternative_explanation": ""},
                "locations": [],
                "no_change_explanation": "",
                "_note": "骨架预填：type/severity/action 为脚本猜测，decision 待 Agent 裁决；误拆请合并，漏拆请补拆。"
            })
        comments.append({"comment_id": cid, "raw_text": raw, "subrequirements": subs})
    return {
        "case_id": case_id,
        "round": 1,
        "language": "zh" if has_cjk(text) else "en",
        "generated_by": "decompose.py",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec='seconds'),
        "skeleton_warning": "本矩阵为自动骨架：子要求只多不少（防漏）。Agent 必须核对：合并误拆、补拆漏拆、逐子要求裁决后再进入后续步骤。",
        "comments": comments,
    }


def main():
    ap = argparse.ArgumentParser(description="reviewer-comments -> matrix.json 骨架（防漏：子要求只多不少）")
    ap.add_argument("--comments", required=True)
    ap.add_argument("--case", default=None)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    if not os.path.exists(a.comments):
        print("[decompose] FATAL: comments file not found: %s" % a.comments, file=sys.stderr)
        sys.exit(2)
    m = build_matrix(a.comments, a.case)
    n_sub = sum(len(c["subrequirements"]) for c in m["comments"])
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(m, f, ensure_ascii=False, indent=2)
    print("[decompose] comments=%d subrequirements=%d -> %s" % (len(m["comments"]), n_sub, a.out))
    print("[decompose] 下一步：Agent 核对骨架（合并误拆/补拆漏拆/逐条裁决），再跑 matrix.py validate")


if __name__ == "__main__":
    main()
