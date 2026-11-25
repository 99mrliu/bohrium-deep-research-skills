#!/usr/bin/env python3
"""context_pack.py — 为指定块组装上下文包（前块已译尾部 + 下块源文头部 + 术语表节选）。

用法: context_pack.py --plan plan.json --state state.json --chunk c003 \
        [--glossary glossary.md] [--tail-chars 600] [--head-chars 300] --out context.md
"""
import argparse, json, os

def load(p):
    return json.load(open(p, encoding="utf-8"))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", required=True)
    ap.add_argument("--state", required=True)
    ap.add_argument("--chunk", required=True)
    ap.add_argument("--glossary")
    ap.add_argument("--tail-chars", type=int, default=600)
    ap.add_argument("--head-chars", type=int, default=300)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    plan = load(a.plan)
    state = load(a.state)
    ids = [c["id"] for c in plan["chunks"]]
    if a.chunk not in ids:
        print(f"ERROR: unknown chunk {a.chunk}", file=sys.stderr)
        raise SystemExit(2)
    idx = ids.index(a.chunk)
    chunk = plan["chunks"][idx]

    L = [f"# 上下文包 · 块 {a.chunk}", ""]
    st = state["chunks"][a.chunk]
    L.append(f"状态: {st['status']}；本块单元数: {len(chunk['units'])}；"
             f"估计词元: {chunk['est_tokens']}")
    L.append("")
    L.append("## 待译单元（全部必须翻译，不得增删单元）")
    for u in chunk["units"]:
        L.append(f"### {u['unit_id']} [{u['kind']}]")
        L.append(u["text"])
        L.append("")
    if idx > 0:
        prev_id = ids[idx - 1]
        pst = state["chunks"][prev_id]
        L.append(f"## 前块（{prev_id}）状态: {pst['status']}")
        if pst["status"] == "done":
            tail = chunk_prev_tail(plan, state, ids, idx, a.tail_chars)
            L.append(tail or "（前块译文尾部不可用）")
        else:
            L.append("（前块未完成：本块翻译须保守处理指代与承接）")
        L.append("")
    if idx + 1 < len(ids):
        nxt = plan["chunks"][idx + 1]
        L.append(f"## 下一块（{nxt['id']}）源文头部（仅供衔接意识，不要翻译）")
        L.append(nxt["source_text"][:a.head_chars])
        L.append("")
    if a.glossary and os.path.exists(a.glossary):
        g = open(a.glossary, encoding="utf-8").read()
        L.append("## 锁定术语表节选")
        L.append(g[:2000])
        L.append("")
    L.append("## 输出契约")
    L.append("写 chunks/{}.translated.json：".format(a.chunk))
    L.append('[{"unit_id":"<与上面一致>","source":"<原文照抄>","translation":"<译文>"}, …]')
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    open(a.out, "w", encoding="utf-8").write("\n".join(L) + "\n")
    print(f"context pack -> {a.out}")

def chunk_prev_tail(plan, state, ids, idx, n):
    """前块已译尾部：从 translations-dir 无法回读时退化为状态说明。"""
    # 译文文本不在 state 中保存（只存哈希）；尾部从上一块 source_text 尾部代替，
    # 由 Agent 依据自己已经产出并持有的前块译文截取。
    prev = plan["chunks"][idx - 1]
    return ("（请从你已产出的前块译文截取末尾 ≤%d 字符作为承接上下文；"
            " 前块源文尾部如下，仅供定位）\n" % n + prev["source_text"][-n:])

if __name__ == "__main__":
    main()
