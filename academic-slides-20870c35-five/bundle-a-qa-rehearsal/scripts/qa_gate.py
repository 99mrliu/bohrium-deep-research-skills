#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""qa_gate.py — 问答预演题库门控 G1–G5（仅 Python3 标准库，无网络依赖）。

输入：

  --bank      qa_bank.json    问答预演题库（questions 数组）
  --deck      deck_plan.json  页级 storyboard（slides 数组；备用页须标 backup:true）
  --claims    claims.json     页级 claim card（含 strength 与 anchor 数字）
  --audience  audience.json   听众画像（objections 数组）

门控规则（每发现一条违例打印一行 "G编号: 具体细节"）：

  G1 类别覆盖：mechanism / data / comparison / limitation 每类至少 1 题。
  G2 引用完整：每题 answer_points ≥ 2 条非空字符串；primary_slide 必须存在于
     deck_plan；backup_slides 每条必须存在且该页 backup:true；
     claim_ids 必须存在于 claims.json。
  G3 口径一致：回答文本中的"数字+单位"token，若与所链 claim 的 anchor 存在
     同单位项，则必须与其中某一个数值完全一致（NFKC + 空白归一后比较，
     数值容差 1e-9 相对误差）；同单位但数值不符即判口径矛盾。
     无单位 token 不参与判定（避免误伤"Figure 2""3 台设备"等）。
  G4 强度纪律：所链 claim 含 preliminary / contextual 时，回答文本不得出现
     过强词：prove / proves / conclusive / definitively（英文词边界匹配、
     大小写不敏感）与 证实 / 确立了（中文子串匹配）。
  G5 质疑覆盖：audience.json 的每个 objection.id 必须被至少 1 题的
     objection_ref 覆盖。

退出码：

  0  全部通过，打印 PASS 汇总
  1  存在门控违例，stdout 逐行打印 "G编号: 细节"
  2  用法 / IO / schema 错误（文件缺失、JSON 损坏、结构不合 schema）

确定性：无随机数、无时间戳，同一输入重复运行输出逐字节一致。
"""

import argparse
import json
import os
import re
import sys
import unicodedata

REQUIRED_CATEGORIES = ["mechanism", "data", "comparison", "limitation"]
WEAK_STRENGTHS = {"preliminary", "contextual"}
EN_STRONG_RE = re.compile(r"\b(proves?|conclusive|definitively)\b", re.IGNORECASE)
ZH_STRONG_WORDS = ["证实", "确立了"]

# 数字 token：可选 "n=" 前缀 + 数值 + 可选单位（字母 / % / ° / µ μ Ω / 开头，
# 后续可含数字，如 mL/min、m/s2）。
NUM_TOKEN_RE = re.compile(
    r"(?:([nN])\s*=\s*)?(-?\d+(?:\.\d+)?)\s*([A-Za-z%°µμΩ/][A-Za-z%°µμΩ/0-9]*)?"
)
# anchor 解析：整串必须是一个"数字+可选单位"（允许 n= 前缀）。
ANCHOR_RE = re.compile(r"^\s*(?:([nN])\s*=\s*)?(-?\d+(?:\.\d+)?)\s*(.*?)\s*$")


class SchemaError(Exception):
    pass


def norm_text(s):
    s = unicodedata.normalize("NFKC", str(s))
    return re.sub(r"\s+", " ", s).strip()


def norm_unit(u):
    return unicodedata.normalize("NFKC", str(u)).casefold().strip()


def parse_anchor(raw):
    """anchor 字符串 → (value, unit_norm)；解析失败返回 None。"""
    m = ANCHOR_RE.match(norm_text(raw))
    if not m:
        return None
    unit = "n=" if m.group(1) else (m.group(3) or "")
    try:
        value = float(m.group(2))
    except ValueError:
        return None
    return value, norm_unit(unit)


def extract_tokens(text):
    """回答文本 → [(value, unit_norm, surface)]；n= 前缀优先于后缀单位。"""
    tokens = []
    for m in NUM_TOKEN_RE.finditer(norm_text(text)):
        unit = "n=" if m.group(1) else (m.group(3) or "")
        tokens.append((float(m.group(2)), norm_unit(unit), m.group(0).strip()))
    return tokens


def load_json(path, label):
    if not os.path.isfile(path):
        raise SchemaError("{} 不存在：{}".format(label, path))
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SchemaError("{} 读取或解析失败：{}".format(label, exc))


def require_str(obj, key, where):
    v = obj.get(key)
    if not isinstance(v, str) or not v.strip():
        raise SchemaError("{} 缺少非空字符串字段 {}".format(where, key))
    return v


def load_bank(path):
    root = load_json(path, "qa_bank.json")
    questions = root.get("questions") if isinstance(root, dict) else None
    if not isinstance(questions, list):
        raise SchemaError("qa_bank.json schema 错误：根对象缺少 questions 数组")
    for i, q in enumerate(questions):
        where = "qa_bank.json 第 {} 题".format(i)
        if not isinstance(q, dict):
            raise SchemaError("{} 不是对象".format(where))
        require_str(q, "id", where)
        require_str(q, "category", where)
        require_str(q, "question", where)
        require_str(q, "primary_slide", where)
        if not isinstance(q.get("answer_points"), list):
            raise SchemaError("{} 的 answer_points 不是数组".format(where))
        if "backup_slides" in q and not isinstance(q["backup_slides"], list):
            raise SchemaError("{} 的 backup_slides 不是数组".format(where))
        if "claim_ids" in q and not isinstance(q["claim_ids"], list):
            raise SchemaError("{} 的 claim_ids 不是数组".format(where))
        if "objection_ref" in q and not isinstance(q["objection_ref"], str):
            raise SchemaError("{} 的 objection_ref 不是字符串".format(where))
    return questions


def load_deck(path):
    root = load_json(path, "deck_plan.json")
    slides = root.get("slides") if isinstance(root, dict) else None
    if not isinstance(slides, list):
        raise SchemaError("deck_plan.json schema 错误：根对象缺少 slides 数组")
    by_id = {}
    for i, s in enumerate(slides):
        where = "deck_plan.json 第 {} 页".format(i)
        if not isinstance(s, dict):
            raise SchemaError("{} 不是对象".format(where))
        sid = require_str(s, "id", where)
        if sid in by_id:
            raise SchemaError("deck_plan.json 存在重复 slide id：{}".format(sid))
        if "backup" in s and not isinstance(s["backup"], bool):
            raise SchemaError("{} 的 backup 不是布尔值".format(where))
        by_id[sid] = s
    return by_id


def load_claims(path):
    root = load_json(path, "claims.json")
    claims = root.get("claims") if isinstance(root, dict) else None
    if not isinstance(claims, list):
        raise SchemaError("claims.json schema 错误：根对象缺少 claims 数组")
    by_id = {}
    for i, c in enumerate(claims):
        where = "claims.json 第 {} 张 claim card".format(i)
        if not isinstance(c, dict):
            raise SchemaError("{} 不是对象".format(where))
        cid = require_str(c, "id", where)
        if cid in by_id:
            raise SchemaError("claims.json 存在重复 claim id：{}".format(cid))
        if "anchor" in c and not isinstance(c["anchor"], list):
            raise SchemaError("{} 的 anchor 不是数组".format(where))
        by_id[cid] = c
    return by_id


def load_objections(path):
    root = load_json(path, "audience.json")
    objections = None
    if isinstance(root, dict):
        if isinstance(root.get("objections"), list):
            objections = root["objections"]
        elif isinstance(root.get("audience"), dict) and isinstance(root["audience"].get("objections"), list):
            objections = root["audience"]["objections"]
    if objections is None:
        raise SchemaError("audience.json schema 错误：找不到 objections 数组")
    ids = []
    for i, ob in enumerate(objections):
        if not isinstance(ob, dict):
            raise SchemaError("audience.json 第 {} 条 objection 不是对象".format(i))
        ids.append(require_str(ob, "id", "audience.json 第 {} 条 objection".format(i)))
    return ids


def check_g1(questions, violations):
    present = {q["category"].strip() for q in questions}
    for cat in REQUIRED_CATEGORIES:
        if cat not in present:
            violations.append("G1: 类别覆盖缺失，{} 类追问为 0 题（四类均须 ≥1）".format(cat))


def check_g2(questions, deck_by_id, claims_by_id, violations):
    for q in questions:
        qid = q["id"]
        points = [p for p in q["answer_points"] if isinstance(p, str) and p.strip()]
        if len(points) < 2:
            violations.append(
                "G2: {} 的 answer_points 非空条目为 {} 条（须 ≥2）".format(qid, len(points)))
        ps = q["primary_slide"].strip()
        if ps not in deck_by_id:
            violations.append("G2: {} 的 primary_slide {!r} 不存在于 deck_plan".format(qid, ps))
        for bs in q.get("backup_slides", []):
            if not isinstance(bs, str) or bs.strip() not in deck_by_id:
                violations.append(
                    "G2: {} 的 backup_slide {!r} 不存在于 deck_plan".format(qid, bs))
            elif not deck_by_id[bs.strip()].get("backup", False):
                violations.append(
                    "G2: {} 的 backup_slide {!r} 在 deck_plan 中未标记 backup:true".format(qid, bs))
        for cid in q.get("claim_ids", []):
            if not isinstance(cid, str) or cid not in claims_by_id:
                violations.append("G2: {} 引用了不存在的 claim id {!r}".format(qid, cid))


def check_g3(questions, claims_by_id, violations):
    for q in questions:
        anchors = []  # (value, unit_norm, raw, claim_id)
        for cid in q.get("claim_ids", []):
            c = claims_by_id.get(cid)
            if not c:
                continue
            for raw in c.get("anchor", []) or []:
                pa = parse_anchor(raw)
                if pa:
                    anchors.append((pa[0], pa[1], str(raw), cid))
        if not anchors:
            continue
        text = " ".join(str(p) for p in q["answer_points"])
        for value, unit, surface in extract_tokens(text):
            if unit == "":
                continue  # 无单位数字不参与口径判定
            same_unit = [a for a in anchors if a[1] == unit]
            if not same_unit:
                continue
            if any(abs(a[0] - value) <= 1e-9 * max(1.0, abs(a[0])) for a in same_unit):
                continue  # 与同单位 anchor 之一精确一致
            _, _, araw, acid = same_unit[0]
            violations.append(
                "G3: {} 回答中的数字 {!r} 与所链 {} 的 anchor {!r} 单位相同但数值冲突".format(
                    q["id"], surface, acid, araw))


def check_g4(questions, claims_by_id, violations):
    for q in questions:
        weak = [(cid, claims_by_id[cid].get("strength", ""))
                for cid in q.get("claim_ids", [])
                if cid in claims_by_id
                and claims_by_id[cid].get("strength") in WEAK_STRENGTHS]
        if not weak:
            continue
        text = norm_text(" ".join(str(p) for p in q["answer_points"]))
        hits = sorted(set(m.group(0) for m in EN_STRONG_RE.finditer(text)), key=str.casefold)
        hits += [w for w in ZH_STRONG_WORDS if w in text]
        for h in hits:
            cid, strength = weak[0]
            violations.append(
                "G4: {} 所链 {} 强度为 {!r}，回答却含过强词 {!r}".format(
                    q["id"], cid, strength, h))


def check_g5(questions, objection_ids, violations):
    covered = {q.get("objection_ref", "").strip() for q in questions} - {""}
    for oid in objection_ids:
        if oid not in covered:
            violations.append(
                "G5: objection {!r} 未被任何题目的 objection_ref 覆盖".format(oid))


def main(argv=None):
    parser = argparse.ArgumentParser(description="问答预演题库门控 G1-G5")
    parser.add_argument("--bank", required=True, help="qa_bank.json 路径")
    parser.add_argument("--deck", required=True, help="deck_plan.json 路径")
    parser.add_argument("--claims", required=True, help="claims.json 路径")
    parser.add_argument("--audience", required=True, help="audience.json 路径")
    args = parser.parse_args(argv)

    try:
        questions = load_bank(args.bank)
        deck_by_id = load_deck(args.deck)
        claims_by_id = load_claims(args.claims)
        objection_ids = load_objections(args.audience)
    except SchemaError as exc:
        print("ERROR: {}".format(exc))
        return 2

    violations = []
    check_g1(questions, violations)
    check_g2(questions, deck_by_id, claims_by_id, violations)
    check_g3(questions, claims_by_id, violations)
    check_g4(questions, claims_by_id, violations)
    check_g5(questions, objection_ids, violations)

    if violations:
        for v in violations:
            print(v)
        print("GATE: FAIL ({} violations across G1-G5)".format(len(violations)))
        return 1
    print("GATE: PASS (G1-G5 clean; {} questions, {} slides, {} claims, {} objections covered)".format(
        len(questions), len(deck_by_id), len(claims_by_id), len(objection_ids)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
