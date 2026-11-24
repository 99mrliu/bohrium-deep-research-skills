#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""qa_seed.py — 问答预演题库播种器（仅 Python3 标准库，无网络依赖）。

从两类结构化输入自动播种一份"追问题库骨架"（qa_bank_seed.json）：

  --claims    claims.json    页级 claim card 数组，每张含
                             id / statement / kind / strength / locator /
                             anchor / limitations / slide
  --audience  audience.json  听众画像，其中 objections 数组每条含
                             id / category / text / likely_claim_ids
  --out       输出路径（qa_bank_seed.json）

播种规则（确定性，无随机数、无时间戳，同一输入重复运行逐字节一致）：

  R1 每张 claim card 的每一条 limitation 必生一题，category=limitation，
     挂到该 claim 与其建议页（claim.slide）。
  R2 每张 strength=preliminary 的 claim 必生一题，category=data
     （数据稳健性追问：样本量、可重复性是否支撑初步结论）。
  R3 audience.json 的每一个 objection 落一题，category 取 objection.category
     （缺省 data），objection_ref 回填 objection.id，供 qa_gate.py 的 G5 核验；
     若 objection 带 likely_claim_ids，则挂接并取其首个 claim 的建议页。

种子题的 answer_points 是三段式占位（重述主张 / 证据定位 / 边界声明，
见 references/qa-taxonomy.md），必须由模型扩写为真实口径后再过
qa_gate.py 的 G1–G5 门控。种子本身不保证过门：类别覆盖（G1）取决于输入，
若 claims 中没有 mechanism/comparison 类素材，须由模型补题。

退出码：0 成功；2 用法 / IO / schema 错误（本脚本不产生门控违例，不用 1）。
"""

import argparse
import json
import os
import sys

ANSWER_PLACEHOLDERS = [
    "【重述主张】待扩写：用一句话重申被追问的结论，不得超出 claim 原文。",
    "【证据定位】待扩写：逐字引用该 claim 的 anchor 数字（含单位）与 locator。",
    "【边界声明】待扩写：声明适用范围与证据强度，弱证据不得用强措辞。",
]


def fail(msg):
    print("ERROR: {}".format(msg))
    sys.exit(2)


def load_json(path, label):
    if not os.path.isfile(path):
        fail("{} 不存在：{}".format(label, path))
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        fail("{} 读取或解析失败：{}".format(label, exc))


def extract_claims(root):
    claims = root.get("claims") if isinstance(root, dict) else None
    if not isinstance(claims, list):
        fail("claims.json schema 错误：根对象缺少 claims 数组")
    for i, c in enumerate(claims):
        if not isinstance(c, dict) or not isinstance(c.get("id"), str) or not c["id"].strip():
            fail("claims.json schema 错误：第 {} 张 claim card 缺少非空字符串 id".format(i))
    return claims


def extract_objections(root):
    objections = None
    if isinstance(root, dict):
        if isinstance(root.get("objections"), list):
            objections = root["objections"]
        elif isinstance(root.get("audience"), dict) and isinstance(root["audience"].get("objections"), list):
            objections = root["audience"]["objections"]
    if objections is None:
        fail("audience.json schema 错误：找不到 objections 数组（audience.objections 或顶层 objections）")
    for i, ob in enumerate(objections):
        if not isinstance(ob, dict) or not isinstance(ob.get("id"), str) or not ob["id"].strip():
            fail("audience.json schema 错误：第 {} 条 objection 缺少非空字符串 id".format(i))
    return objections


def main(argv=None):
    parser = argparse.ArgumentParser(description="问答预演题库播种器（limitations / preliminary / objections → 种子题）")
    parser.add_argument("--claims", required=True, help="claims.json 路径")
    parser.add_argument("--audience", required=True, help="audience.json 路径")
    parser.add_argument("--out", required=True, help="输出 qa_bank_seed.json 路径")
    args = parser.parse_args(argv)

    claims = extract_claims(load_json(args.claims, "claims.json"))
    objections = extract_objections(load_json(args.audience, "audience.json"))
    slide_of = {c["id"]: c.get("slide", "") for c in claims}

    questions = []
    seq = 0
    n_lim = n_pre = n_obj = 0

    def add(category, question, claim_ids, objection_ref, primary_slide):
        nonlocal seq
        seq += 1
        questions.append({
            "id": "SEED-Q-{:02d}".format(seq),
            "category": category,
            "question": question,
            "claim_ids": claim_ids,
            "objection_ref": objection_ref,
            "primary_slide": primary_slide,
            "backup_slides": [],
            "answer_points": list(ANSWER_PLACEHOLDERS),
            "status": "seed",
        })

    # R1：每条 limitation 必生一题
    for c in claims:
        for lim in c.get("limitations") or []:
            add("limitation",
                "局限追问：{}。这一限制对结论的适用范围意味着什么？".format(lim),
                [c["id"]], "", slide_of.get(c["id"], ""))
            n_lim += 1

    # R2：每条 preliminary claim 必生一题（数据稳健性）
    for c in claims:
        if c.get("strength") == "preliminary":
            add("data",
                "数据稳健性追问：{}。该结论标注为 preliminary，样本量与可重复性是否足以支撑？".format(c.get("statement", c["id"])),
                [c["id"]], "", slide_of.get(c["id"], ""))
            n_pre += 1

    # R3：每个 objection 落一题
    for ob in objections:
        claim_ids = [cid for cid in (ob.get("likely_claim_ids") or []) if cid in slide_of]
        primary = slide_of.get(claim_ids[0], "") if claim_ids else ""
        add(ob.get("category", "data"),
            ob.get("text", ""),
            claim_ids, ob["id"], primary)
        n_obj += 1

    bank = {
        "_note": "由 qa_seed.py 自动播种的题库骨架；answer_points 为三段式占位，"
                 "须按 references/qa-taxonomy.md 扩写、补备用页后用 qa_gate.py 过 G1-G5。",
        "questions": questions,
    }

    out_dir = os.path.dirname(os.path.abspath(args.out))
    if out_dir and not os.path.isdir(out_dir):
        os.makedirs(out_dir, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(bank, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    print("SEED: {} questions (limitation={}, preliminary-data={}, objection={})".format(
        len(questions), n_lim, n_pre, n_obj))
    print("SEED: objections covered: {}".format(
        ", ".join(ob["id"] for ob in objections) if objections else "(none)"))
    print("SEED: written -> {}".format(args.out))
    sys.exit(0)


if __name__ == "__main__":
    main()
