#!/usr/bin/env python3
"""evidence_map.py — "证据定位"工具：段落索引、数值-单位抽取、按题候选排序与数量冲突扫描。

子命令：
  index     解析案例包，为每段建立词项统计，抽取全部"数值+单位"提及
            （含上下文窗口），写 index.json 与 numbers.md 数值总表。
  query     对单个问题（BM25-lite，k1=1.5 / b=0.75）返回候选段落排序，
            附带每段命中的数值提及，供定向阅读。
  subqs     把复合中文问题拆成子问清单（按 ？?；;、以及/和 等切分），
            逐子问做候选排序，输出 evidence_map.md。
  conflicts 对给定数量关键词（如 "surface area"）列出跨段落的全部数值提及；
            同关键词出现两个以上不同数值时给出 CONFLICT 提示。
            机械部分只负责抽取与比对，判定由模型完成。

只用标准库。所有路径显式传入。
"""
import argparse
import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

WORD_RE = re.compile(r"[a-z0-9][a-z0-9\-]*")
NUM_RE = re.compile(
    r"(?<![A-Za-z0-9])([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)\s?"
    r"([a-zA-Zμµ°%²³/·\-\^]+)?")
CJK_SPLIT_RE = re.compile(r"[？?；;。]|\s+以及\s+|\s+和\s+")


def load_case(path):
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    paras = raw.get("paragraphs") or raw.get("sections") or []
    norm = []
    for i, p in enumerate(paras):
        if isinstance(p, dict):
            pid = p.get("paragraph_id") or p.get("id") or f"P{i + 1}"
            text = p.get("text") or p.get("content") or ""
            norm.append((str(pid), str(text)))
        else:
            m = re.match(r"^\s*([A-Za-z0-9_.\-]+)\s*(.*)$", str(p), re.S)
            pid, text = (m.group(1), m.group(2)) if m else (f"P{i + 1}", str(p))
            norm.append((pid, text))
    for key, pre in (("tables", "T"), ("figure_captions", "F"), ("references", "R")):
        for j, item in enumerate(raw.get(key) or []):
            norm.append((f"{pre}{j + 1}", item if isinstance(item, str) else json.dumps(item, ensure_ascii=False)))
    qs = raw.get("questions") or []
    questions = []
    for i, q in enumerate(qs):
        if isinstance(q, dict):
            questions.append((str(q.get("question_id") or f"Q{i + 1}"), str(q.get("text") or q.get("question") or "")))
        else:
            questions.append((f"Q{i + 1}", str(q)))
    return {"case_id": str(raw.get("case_id") or raw.get("id")),
            "paper_id": str(raw.get("paper_id") or raw.get("paper") or ""),
            "material_version": str(raw.get("material_version") or raw.get("version") or ""),
            "paragraphs": norm, "questions": questions,
            "output_contract": raw.get("output_contract") or {}}


def tokens(text):
    return [w for w in WORD_RE.findall(text.lower())
            if len(w) > 1 or w.isdigit()]


def mentions(text, window=45):
    """抽取数值提及：[(value, unit, context_snippet, pos, pre_context)]。"""
    out = []
    for m in NUM_RE.finditer(text):
        unit = (m.group(2) or "").strip(" ,.;:()[]")
        ctx = text[max(0, m.start() - window):m.end() + window].replace("\n", " ")
        pre = text[max(0, m.start() - 60):m.start()].lower()
        out.append((m.group(1), unit, ctx.strip(), m.start(), pre))
    return out


def build_index(case):
    docs, df = [], Counter()
    for pid, text in case["paragraphs"]:
        toks = tokens(text)
        tf = Counter(toks)
        df.update(set(tf))
        docs.append({"paragraph_id": pid, "text": text, "tf": dict(tf),
                     "len": len(toks), "mentions": mentions(text)})
    n = max(1, len(docs))
    for d in docs:
        d["idf"] = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items() if t in d["tf"]}
    return {"case": {"case_id": case["case_id"], "paper_id": case["paper_id"],
                     "material_version": case["material_version"]},
            "n_docs": len(docs), "docs": docs,
            "questions": [{"question_id": qid, "text": t} for qid, t in case["questions"]],
            "output_contract": case["output_contract"]}


def bm25(index, query, terms=None, top=8):
    """query 可为中文/英文混合文本；terms 为模型翻译出的英文关键词列表，
    与 query 的词项流合并后检索。"""
    qtf = Counter(tokens(query))
    for t in terms or []:
        for w in tokens(t):
            qtf[w] = max(qtf[w], 2)
    if not qtf:
        return []
    avg = sum(d["len"] for d in index["docs"]) / max(1, len(index["docs"]))
    scored = []
    for d in index["docs"]:
        s = 0.0
        for t, qf in qtf.items():
            idf = d["idf"].get(t, 0.0)
            if idf <= 0:
                continue
            f = d["tf"].get(t, 0)
            s += idf * f * 2.2 / (f + 1.2 * (1 - 0.75 + 0.75 * d["len"] / max(avg, 1))) * min(qf, 2)
        if s > 0:
            hit_mentions = [mn for mn in d["mentions"]
                            if any(w in mn[2].lower() for w in qtf)]
            scored.append((round(s, 3), d["paragraph_id"], hit_mentions))
    scored.sort(reverse=True)
    return scored[:top]


def split_subquestions(qtext):
    parts = [p.strip() for p in CJK_SPLIT_RE.split(qtext) if p and p.strip()]
    # 保留原始顺序、去掉完全重复项
    seen, out = set(), []
    for p in parts:
        if p not in seen:
            seen.add(p); out.append(p)
    return out


def cmd_index(args):
    work = Path(args.work); work.mkdir(parents=True, exist_ok=True)
    case = load_case(args.case)
    index = build_index(case)
    (work / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
    lines = ["# 数值-单位总表", "",
             "| 段落 | 数值 | 单位 | 上下文 |", "|-|-:|-|-|"]
    n = 0
    for d in index["docs"]:
        for value, unit, ctx, pos, pre in d["mentions"]:
            lines.append(f"| {d['paragraph_id']} | {value} | {unit or '—'} | {ctx} |")
            n += 1
    (work / "numbers.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"index ok: {len(index['docs'])} paragraphs, {n} numeric mentions -> {work}")


def fmt_hits(hits):
    out = []
    for score, pid, mns in hits:
        line = f"  - {pid} (score {score})"
        if mns:
            v, u = mns[0][0], mns[0][1]
            line += f"  含数值提及 {v} {u or ''}".rstrip()
        out.append(line)
    return "\n".join(out) if out else "  （无命中：先把子问翻译为英文关键词，用 --terms 传入后重试）"


def cmd_query(args):
    index = json.loads(Path(args.index).read_text(encoding="utf-8"))
    hits = bm25(index, args.text, terms=args.terms)
    print(f"query: {args.text}\n" + fmt_hits(hits))


def cmd_subqs(args):
    index = json.loads(Path(args.index).read_text(encoding="utf-8"))
    term_map = {}
    if args.terms:
        # --terms 形如 "Q1S1:yield strength,modulus;Q2S2:fatigue life"
        for item in args.terms.split(";"):
            if ":" in item:
                k, v = item.split(":", 1)
                term_map[k.strip()] = v.split(",")
    lines = ["# 证据地图（evidence map）", "",
             "> 用法：对每个子问先人工/模型翻译出英文关键词（本表已按 --terms 注入），",
             "> 定向阅读候选段落后回到该段核对数值-单位总表。", ""]
    for q in index["questions"]:
        lines.append(f"## {q['question_id']} {q['text']}")
        for i, sub in enumerate(split_subquestions(q["text"]), 1):
            tag = f"{q['question_id']}S{i}"
            terms = term_map.get(tag)
            lines.append(f"### 子问{i}：{sub}" + (f"（terms: {', '.join(terms)}）" if terms else ""))
            lines.append(fmt_hits(bm25(index, sub, terms=terms)))
            lines.append("")
    report = "\n".join(lines)
    (Path(args.work) / "evidence_map.md").write_text(report, encoding="utf-8")
    print(report)


def cmd_conflicts(args):
    """数量冲突扫描：机械抽取 + 精确比对，判定留给模型。

    三类输出：
      CONFLICT  —— 同一关键词、同一数值前语境（前 40 字符归一化相同）出现不同值；
      MULTIVALUE —— 同一单位下有多个不同取值（多为不同对象，需逐段并列说明）；
      NONE —— 唯一取值或无提及。
    """
    index = json.loads(Path(args.index).read_text(encoding="utf-8"))
    key = args.key.lower()
    rows = []
    for d in index["docs"]:
        for value, unit, ctx, pos, pre in d["mentions"]:
            # 数值位置与关键词的距离必须小于 80 字符，避免误收邻近数值
            kpos = d["text"].lower().rfind(key, 0, pos + len(value))
            kpos2 = d["text"].lower().find(key, pos)
            near = (kpos != -1 and pos - kpos < 90) or (kpos2 != -1 and kpos2 - pos < 90)
            if near:
                rows.append((d["paragraph_id"], value, unit or "—", ctx, pre))
    print(f"# 关键词「{args.key}」邻近的全部数值提及（{len(rows)} 条）")
    for pid, v, u, ctx, _ in rows:
        print(f"- {pid}: {v} {u}\n  …{ctx}…")
    if not rows:
        print("\nNONE: 无提及；该数量可能未被材料报告——通读相关章节后再定 status。")
        sys.exit(4)
    # 同语境不同值 = 真冲突
    ctx2val = {}
    for pid, v, u, _, pre in rows:
        sig = re.sub(r"[-+]?\d+(?:\.\d+)?", "#", pre[-40:]) + "|" + u
        ctx2val.setdefault(sig, set()).add(v)
    conflicts = {sig: vals for sig, vals in ctx2val.items() if len(vals) > 1}
    if conflicts:
        print("\nCONFLICT: 相同语境出现不同数值：")
        for sig, vals in conflicts.items():
            print(f"  语境 {sig!r}: 值 {sorted(vals)} —— 并列给出各值及段落出处，不得二选一。")
        sys.exit(3)
    by_unit = defaultdict(set)
    for _, v, u, _, _ in rows:
        by_unit[u].add(v)
    multi = {u: sorted(vs) for u, vs in by_unit.items() if len(vs) > 1}
    if multi:
        print(f"\nMULTIVALUE: 同一单位下出现多个取值 {multi}。"
              " 多数情况对应不同对象/条件，作答时逐段保留对象与条件，不得混写。")
    else:
        print("\nNONE: 取值唯一，未发现冲突。")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("index"); p.add_argument("--case", required=True); p.add_argument("--work", required=True)
    p = sub.add_parser("query"); p.add_argument("--index", required=True)
    p.add_argument("--text", required=True); p.add_argument("--top", type=int, default=8)
    p.add_argument("--terms", nargs="*", default=None,
                   help="英文关键词（模型把中文子问翻译后传入），与问题词项合并检索")
    p = sub.add_parser("subqs"); p.add_argument("--index", required=True); p.add_argument("--work", required=True)
    p.add_argument("--terms", default=None,
                   help="形如 \"Q1S1:yield strength,modulus;Q2S2:fatigue life\"")
    p = sub.add_parser("conflicts"); p.add_argument("--index", required=True); p.add_argument("--key", required=True)
    args = ap.parse_args()
    sys.exit({"index": cmd_index, "query": cmd_query,
              "subqs": cmd_subqs, "conflicts": cmd_conflicts}[args.cmd](args))


if __name__ == "__main__":
    main()
