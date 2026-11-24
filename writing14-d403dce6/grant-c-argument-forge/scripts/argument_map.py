#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""argument_map.py — 立项依据必要性论证链解析与判定。

解析章节稿 markdown 中“立项依据”小节为句子序列，依据 references/role_cues.md 的
线索词表把句子分类为：现状/瓶颈/已有进展/差距/切入点/团队凭据/时机/口号/未分类。

产出 <outdir>/argument_map.json：
  - role_sequence：逐句角色与行号、是否带引文标记；
  - chain：必要角色 现状→瓶颈→差距→切入点 是否齐备且首次出现次序合理；
  - citation_coverage：事实类句子（需引文=是）的引文覆盖率与阈值判定；
  - unclassified：未分类句清单。

退出码：0 链完整且覆盖率达标；1 链不完整或事实句引文覆盖率 < 阈值（默认 0.8）；
2 用法/IO 错误。仅使用 Python3 标准库；确定性输出。
"""
import argparse
import json
import os
import re
import sys

CITATION_RE = re.compile(
    r"(\[[0-9]+\]|〔[^〕]*〕|（[^）]*(?:19|20)\d{2}[^）]*）|\([A-Za-z][^)]*(?:19|20)\d{2}[^)]*\))"
)
HEADING_RE = re.compile(r"^(#{1,6})\s*(.+?)\s*$")
ROLE_BLOCK_RE = re.compile(r"^##\s*角色：\s*(\S+)\s*$")
CHAIN_REQUIRED = ["现状", "瓶颈", "差距", "切入点"]


def load_role_cues(path):
    """解析 role_cues.md 的机器可读块，返回 [{name, cues, priority, need_citation}]。"""
    with open(path, encoding="utf-8") as f:
        lines = f.read().split("\n")
    roles = []
    cur = None
    in_code = False
    for line in lines:
        if line.strip().startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        m = ROLE_BLOCK_RE.match(line)
        if m:
            cur = {"name": m.group(1), "cues": [], "priority": 0, "need_citation": False}
            roles.append(cur)
            continue
        if cur is None:
            continue
        s = line.strip()
        if s.startswith("- 线索词："):
            cur["cues"] = [c for c in s[len("- 线索词："):].split("|") if c]
        elif s.startswith("- 优先级："):
            cur["priority"] = int(s[len("- 优先级："):].strip())
        elif s.startswith("- 需引文："):
            cur["need_citation"] = s[len("- 需引文："):].strip() == "是"
    if not roles:
        raise ValueError("线索词表 %s 中未解析到任何「## 角色：」块" % path)
    roles.sort(key=lambda r: -r["priority"])
    return roles


def find_section(lines, keyword):
    for i, line in enumerate(lines):
        m = HEADING_RE.match(line)
        if m and keyword in m.group(2):
            level = len(m.group(1))
            j = i + 1
            while j < len(lines):
                m2 = HEADING_RE.match(lines[j])
                if m2 and len(m2.group(1)) <= level:
                    break
                j += 1
            return i, j
    return None


def split_sentences(lines, start, end):
    """把 [start,end) 行范围切成句子，返回 [(text, line_no)]。

    中文稿件常在句中硬换行，故换行不作为句子边界；仅按 。！？； 切分，
    句子起始行号由其在拼接文本中的偏移折算。"""
    body = "\n".join(lines[start + 1:end])
    base_line = start + 2  # 小节标题的下一行为第 1 行正文
    sentences, buf, buf_start = [], "", 0
    for i, ch in enumerate(body):
        if not buf and ch in "\n \t　":
            buf_start = i + 1
            continue
        buf += ch
        if ch in "。！？；":
            s = buf.strip()
            if s:
                sentences.append((s, base_line + body.count("\n", 0, buf_start)))
            buf, buf_start = "", i + 1
    if buf.strip():
        sentences.append((buf.strip(), base_line + body.count("\n", 0, buf_start)))
    return sentences


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="解析“立项依据”小节为角色句序列，判定必要性论证链完整性与事实句引文覆盖率。"
    )
    ap.add_argument("input", help="章节稿 markdown 文件路径")
    ap.add_argument("-o", "--outdir", default=".", help="输出目录（默认当前目录）")
    ap.add_argument("--cues", default=None,
                    help="角色线索词表（默认脚本上级 references/role_cues.md）")
    ap.add_argument("--section", default="立项依据", help="小节标题关键词（默认：立项依据）")
    ap.add_argument("--threshold", type=float, default=0.8,
                    help="事实句引文覆盖率阈值（默认 0.8）")
    args = ap.parse_args(argv)

    cues_path = args.cues or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), os.pardir, "references", "role_cues.md")
    try:
        with open(args.input, encoding="utf-8") as f:
            lines = f.read().split("\n")
    except OSError as e:
        print("错误：无法读取输入文件 %s：%s" % (args.input, e), file=sys.stderr)
        return 2
    try:
        roles = load_role_cues(cues_path)
    except (OSError, ValueError) as e:
        print("错误：%s" % e, file=sys.stderr)
        return 2

    sec = find_section(lines, args.section)
    if not sec:
        print("错误：未找到标题含「%s」的小节" % args.section, file=sys.stderr)
        return 2

    sentences = split_sentences(lines, sec[0], sec[1])
    role_seq, unclassified = [], []
    first_occurrence = {}
    for sid, (sent, ln) in enumerate(sentences, 1):
        role = "未分类"
        for r in roles:
            if any(re.search(cue, sent) for cue in r["cues"]):
                role = r["name"]
                break
        cited = bool(CITATION_RE.search(sent))
        role_seq.append({"id": sid, "line": ln, "text": sent, "role": role, "cited": cited})
        if role == "未分类":
            unclassified.append({"id": sid, "line": ln, "text": sent})
        elif role not in first_occurrence:
            first_occurrence[role] = sid

    need_cite = {r["name"] for r in roles if r["need_citation"]}
    factual = [s for s in role_seq if s["role"] in need_cite]
    cited_n = sum(1 for s in factual if s["cited"])
    ratio = (cited_n / len(factual)) if factual else 1.0

    present = {r: (r in first_occurrence) for r in CHAIN_REQUIRED}
    order = [first_occurrence[r] for r in CHAIN_REQUIRED if r in first_occurrence]
    order_ok = len(order) == len(CHAIN_REQUIRED) and order == sorted(order)
    complete = all(present.values()) and order_ok

    result = {
        "input": os.path.abspath(args.input),
        "section": args.section,
        "role_sequence": role_seq,
        "chain": {
            "required": CHAIN_REQUIRED,
            "present": present,
            "first_occurrence": first_occurrence,
            "order_ok": order_ok,
            "complete": complete,
        },
        "citation_coverage": {
            "factual_roles": sorted(need_cite),
            "total_factual": len(factual),
            "cited": cited_n,
            "ratio": round(ratio, 4),
            "threshold": args.threshold,
            "pass": ratio >= args.threshold,
        },
        "unclassified": unclassified,
    }
    try:
        os.makedirs(args.outdir, exist_ok=True)
        with open(os.path.join(args.outdir, "argument_map.json"), "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2, sort_keys=True)
    except OSError as e:
        print("错误：写出产物失败：%s" % e, file=sys.stderr)
        return 2

    print("argument_map: 句子 %d 句；链完整=%s（缺失：%s；次序合理=%s）；事实句引文覆盖率 %.2f/%0.2f；未分类 %d 句" % (
        len(sentences), complete,
        "无" if all(present.values()) else "、".join(r for r in CHAIN_REQUIRED if not present[r]),
        order_ok, ratio, args.threshold, len(unclassified)))
    ok = complete and ratio >= args.threshold
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
