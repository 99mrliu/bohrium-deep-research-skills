#!/usr/bin/env python3
"""claim_lint.py — 论断表达质量检查器。

子命令：
  scaffold  为每个问题生成"论断写作模板"（markdown），内嵌语法提示。
  lint      对拟提交的 result.json 做表达质量检查（不改写内容）：
            E1 引文必须逐字存在于所引段落；E2 论断中的每个数值必须出现在
            该论断的引文中；E3 status 与 unanswered_parts 自洽；E4 reported
            论断必须有证据；E5 字段与问题覆盖完整；W1 kind 与措辞类型
            不一致提示；W2 条件词出现但 conditions 为空；W3 引文过长；
            W4 未用中文作答。ERROR 非零退出。

检查只报告、不修改——改写是作者（模型）的工作。标准库实现。
"""
import argparse
import json
import re
import sys
from pathlib import Path

CJK_RE = re.compile(r"[一-鿿]")
NUM_RE = re.compile(r"(?<![A-Za-z0-9.])[-+]?\d+(?:\.\d+)?(?![A-Za-z0-9])")
INFER_MARK = re.compile(r"综合|对比可知|可推知|推断|换算|计算得出|约为.*计算|由 P\d|inferred|estimate", re.I)
COND_MARK = re.compile(
    r"(at room temperature|under|following|anneal|degrees?|°C|mW/cm|atm|MPa|GPa|"
    r"mm/s|mm/min|mg/L|rpm|percent of|at \d)", re.I)
STATUS_ENUM = {"answered", "partial", "insufficient_evidence", "input_error"}


def load_case(path):
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    paras = raw.get("paragraphs") or raw.get("sections") or []
    norm = {}
    for i, p in enumerate(paras):
        if isinstance(p, dict):
            pid = str(p.get("paragraph_id") or p.get("id") or f"P{i + 1}")
            text = str(p.get("text") or p.get("content") or "")
        else:
            m = re.match(r"^\s*([A-Za-z0-9_.\-]+)\s*(.*)$", str(p), re.S)
            pid, text = (m.group(1), m.group(2)) if m else (f"P{i + 1}", str(p))
        norm[pid] = " ".join(text.split())
    qs = raw.get("questions") or []
    questions = [(str(q.get("question_id") or f"Q{i + 1}"), str(q.get("text") or q.get("question") or ""))
                 if isinstance(q, dict) else (f"Q{i + 1}", str(q)) for i, q in enumerate(qs)]
    return norm, questions


def norm_ws(s):
    return " ".join(str(s).split())


def cmd_scaffold(args):
    work = Path(args.work); work.mkdir(parents=True, exist_ok=True)
    _, questions = load_case(args.case)
    for qid, qtext in questions:
        tpl = f"""# {qid} 论断写作单（草稿，不是最终文件）

题目：{qtext}

## 论断语法（每条论断独立成卡）

- CLAIM reported | 中文论断（一句一个可核对事实，含数值+单位+条件） | P<段号> "逐字引文"
- CLAIM inferred | 中文推断（开头写"由 P…与 P…对比可知"） | P<段号> "引文" ; P<段号> "引文"
- NOTE insufficient | 材料未报告的子问 | 已核对段落：P1, P2, ...

## 规则提示

1. 原文报告的数值/事实 → reported；自己比较、换算、组合出的 → inferred。
2. 作者解释（"作者认为/归因于"）是 reported，但 text 中必须出现"作者"二字。
3. 每个数值连同条件；条件也进下方的 conditions 列表。
4. 冲突：两条说法各写一条 CLAIM，附各自段落，不取舍。
5. 未报告：NOTE insufficient 必须列出核对过的段落编号。

## 论断区

（在此写 CLAIM / NOTE 行）

## conditions

（结论成立的实验条件列表）

## 缺口

（无法回答的子问及原因）
"""
        (work / f"{qid}.md").write_text(tpl, encoding="utf-8")
    print(f"scaffold ok: {len(questions)} question sheet(s) -> {work}")


def cmd_lint(args):
    paras, questions = load_case(args.case)
    result = json.loads(Path(args.result).read_text(encoding="utf-8"))
    errors, warns = [], []

    qids = [q[0] for q in questions]
    got = [a.get("question_id") for a in result.get("answers", [])]
    if set(got) != set(qids):  # E5
        errors.append(f"E5 问题覆盖不一致：缺 {sorted(set(qids) - set(got))}，多 {sorted(set(got) - set(qids))}")

    for a in result.get("answers", []):
        qid = a.get("question_id", "?")
        status = a.get("status")
        if status not in STATUS_ENUM:  # E5
            errors.append(f"E5 {qid}: status 非法 {status!r}")
        if not str(a.get("answer", "")).strip():
            errors.append(f"E5 {qid}: answer 为空")
        elif not CJK_RE.search(a["answer"]):  # W4
            warns.append(f"W4 {qid}: answer 未见中文")
        ups = a.get("unanswered_parts") or []
        if status == "answered" and ups:  # E3
            errors.append(f"E3 {qid}: status=answered 但 unanswered_parts 非空")
        if status in ("partial", "insufficient_evidence") and not ups:
            warns.append(f"E3 {qid}: status={status} 建议填写 unanswered_parts 说明缺口")
        if status == "insufficient_evidence" and not re.search(r"未报告|无法确定|核对|未提及", str(a.get("answer", ""))):
            warns.append(f"E3 {qid}: insufficient_evidence 应在 answer 中说明核对了哪些段落")
        for up in ups:
            if not up.get("part") or not up.get("reason"):
                errors.append(f"E3 {qid}: unanswered_parts 条目缺 part 或 reason")

        seen = set()
        for c in a.get("claims", []):
            cid = c.get("claim_id", "?")
            if cid in seen:
                errors.append(f"E5 {qid}/{cid}: claim_id 重复")
            seen.add(cid)
            kind, text = c.get("kind"), str(c.get("text", ""))
            evs = c.get("evidence") or []
            if kind not in ("reported", "inferred"):
                errors.append(f"E5 {qid}/{cid}: kind 非法 {kind!r}")
            if kind == "reported" and not evs:  # E4
                errors.append(f"E4 {qid}/{cid}: reported 论断必须有证据")
            quotes_text = ""
            for ev in evs:
                pid, quote = ev.get("paragraph_id"), norm_ws(ev.get("quote", ""))
                if pid not in paras:
                    errors.append(f"E1 {qid}/{cid}: 证据段落 {pid} 不在材料清单")
                elif quote not in paras[pid]:
                    errors.append(f"E1 {qid}/{cid}: 引文不逐字（{pid}）: {quote[:50]!r}")
                if len(quote.split()) > 60:
                    warns.append(f"W3 {qid}/{cid}: 引文 >60 词，建议截短")
                quotes_text += " " + quote
            # E2: 论断中的数值必须能在引文中找到
            for num in set(NUM_RE.findall(text)):
                if num not in quotes_text:
                    errors.append(f"E2 {qid}/{cid}: 论断数值 {num} 未出现在该论断引文中")
            # W1: kind 与措辞
            if kind == "reported" and INFER_MARK.search(text):
                warns.append(f"W1 {qid}/{cid}: 措辞像推断但标了 reported，确认 kind")
            # W2: 条件词与 conditions
            if COND_MARK.search(quotes_text) and not a.get("conditions"):
                warns.append(f"W2 {qid}: 引文含条件词但 conditions 为空")

    for e in errors:
        print("ERROR:", e)
    for w in warns:
        print("WARN:", w)
    print(f"lint done: {len(errors)} error(s), {len(warns)} warn(s)")
    return 1 if errors else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("scaffold"); p.add_argument("--case", required=True); p.add_argument("--work", required=True)
    p = sub.add_parser("lint"); p.add_argument("--case", required=True); p.add_argument("--result", required=True)
    args = ap.parse_args()
    sys.exit(cmd_scaffold(args) if args.cmd == "scaffold" else cmd_lint(args))


if __name__ == "__main__":
    main()
