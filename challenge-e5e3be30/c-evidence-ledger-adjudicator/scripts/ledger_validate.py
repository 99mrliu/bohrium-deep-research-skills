#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ledger_validate.py — 台账 schema 与标注一致性机检。

用法:
    python3 ledger_validate.py PATH [PATH ...]

PATH 可为单个台账 JSON 或目录（扫描其中 ledger-*.json）。

检查分两级:
  ERROR   schema 硬错误（字段缺失/类型错误/非法枚举/covers 引用不存在的锚点）
          → 打印并阻塞，退出码 1。
  WARNING 标注一致性问题（不阻塞，退出码仍为 0）:
    W1 direct 证据 covers 为空
    W2 topical 证据却覆盖全部锚点（疑似把"主题相关"当成"直接证据"）
    W3 adjudication.verdict=contradicted 但无 strength=direct 且 polarity=opposite 的证据
    W4 adjudication.verdict=supported 但无 strength=direct 且 polarity=same 的证据
    W5 side 与 polarity 标注不一致（pro+opposite / con+same）
    W6 adjudication.verdict=partially_supported/supported 但台账完全无 pro 证据

退出码: 0 通过（可含 WARNING）; 1 存在 schema ERROR; 2 IO/用法错误。
纯 Python3 标准库。
"""
import argparse
import glob
import json
import os
import sys

SIDES = {"pro", "con"}
STRENGTHS = {"direct", "indirect", "topical"}
POLARITIES = {"same", "opposite"}
ANCHOR_TYPES = {"number", "comparator", "negation", "condition", "causal",
                "quantifier"}
VERDICTS = {"supported", "partially_supported", "contradicted",
            "insufficient_evidence"}


def iter_ledger_paths(paths):
    out = []
    for p in paths:
        if os.path.isdir(p):
            out.extend(sorted(glob.glob(os.path.join(p, "ledger-*.json"))))
        elif os.path.isfile(p):
            out.append(p)
        else:
            print("ERROR: 路径不存在: %s" % p, file=sys.stderr)
            sys.exit(2)
    if not out:
        print("ERROR: 未找到任何台账文件", file=sys.stderr)
        sys.exit(2)
    return out


def validate_ledger(ledger, path):
    errors, warnings = [], []

    def err(msg):
        errors.append(msg)

    def warn(msg):
        warnings.append(msg)

    for key in ("schema_version", "claim_id", "claim_text", "anchors",
                "evidence"):
        if key not in ledger:
            err("缺少顶层字段 '%s'" % key)
    if errors:
        return errors, warnings
    if not isinstance(ledger["anchors"], list):
        err("'anchors' 必须为列表")
        return errors, warnings
    if not isinstance(ledger["evidence"], list):
        err("'evidence' 必须为列表")
        return errors, warnings
    if "adjudication" not in ledger:
        err("缺少顶层字段 'adjudication'（可为 null）")
        return errors, warnings

    anchor_ids = set()
    for i, a in enumerate(ledger["anchors"]):
        if not isinstance(a, dict):
            err("anchors[%d] 不是对象" % i)
            continue
        for k in ("id", "type", "text", "core"):
            if k not in a:
                err("anchors[%d] 缺少字段 '%s'" % (i, k))
        if a.get("id") in anchor_ids:
            err("锚点 id 重复: %s" % a.get("id"))
        anchor_ids.add(a.get("id"))
        if a.get("type") not in ANCHOR_TYPES:
            err("锚点 %s 类型非法: %s" % (a.get("id"), a.get("type")))
        if not isinstance(a.get("core"), bool):
            err("锚点 %s 的 core 必须为布尔值" % a.get("id"))

    ev_ids = set()
    for i, e in enumerate(ledger["evidence"]):
        tag = "evidence[%d](%s)" % (i, e.get("evidence_id", "?")) \
            if isinstance(e, dict) else "evidence[%d]" % i
        if not isinstance(e, dict):
            err("%s 不是对象" % tag)
            continue
        for k in ("evidence_id", "side", "strength", "polarity", "covers",
                  "quote", "page", "section"):
            if k not in e:
                err("%s 缺少字段 '%s'" % (tag, k))
        if e.get("evidence_id") in ev_ids:
            err("evidence_id 重复: %s" % e.get("evidence_id"))
        ev_ids.add(e.get("evidence_id"))
        if e.get("side") not in SIDES:
            err("%s side 非法: %s（应为 pro/con）" % (tag, e.get("side")))
        if e.get("strength") not in STRENGTHS:
            err("%s strength 非法: %s" % (tag, e.get("strength")))
        if e.get("polarity") not in POLARITIES:
            err("%s polarity 非法: %s" % (tag, e.get("polarity")))
        if not isinstance(e.get("covers"), list):
            err("%s covers 必须为列表" % tag)
        else:
            for aid in e["covers"]:
                if aid not in anchor_ids:
                    err("%s covers 引用了不存在的锚点: %s" % (tag, aid))
        if not e.get("quote") or not isinstance(e.get("quote"), str):
            err("%s quote 必须为非空字符串（逐字原文）" % tag)
        if e.get("page") is not None and not isinstance(e.get("page"), int):
            err("%s page 必须为整数或 null" % tag)
        if e.get("section") is not None and not isinstance(e.get("section"), str):
            err("%s section 必须为字符串或 null" % tag)

        if errors and errors[-1].startswith(tag):
            continue  # 已有硬错误，跳过一致性检查
        covers = set(e.get("covers") or [])
        if e.get("strength") == "direct" and not covers:
            warn("W1 %s: direct 证据 covers 为空（direct 必须落到具体锚点）" % tag)
        if e.get("strength") == "topical" and anchor_ids and \
                anchor_ids <= covers:
            warn("W2 %s: topical 证据却覆盖全部锚点"
                 "（疑似把主题相关当作直接证据，请复核强度档）" % tag)
        if e.get("side") == "pro" and e.get("polarity") == "opposite":
            warn("W5 %s: side=pro 但 polarity=opposite，标注不一致" % tag)
        if e.get("side") == "con" and e.get("polarity") == "same":
            warn("W5 %s: side=con 但 polarity=same，标注不一致" % tag)

    adj = ledger.get("adjudication")
    if adj is not None:
        if not isinstance(adj, dict) or adj.get("verdict") not in VERDICTS:
            err("adjudication.verdict 缺失或非法（应为 %s）"
                % "/".join(sorted(VERDICTS)))
        else:
            v = adj["verdict"]
            has_dir_opp = any(
                isinstance(e, dict) and e.get("strength") == "direct"
                and e.get("polarity") == "opposite"
                for e in ledger["evidence"])
            has_dir_same = any(
                isinstance(e, dict) and e.get("strength") == "direct"
                and e.get("polarity") == "same"
                for e in ledger["evidence"])
            has_pro = any(isinstance(e, dict) and e.get("side") == "pro"
                          for e in ledger["evidence"])
            if v == "contradicted" and not has_dir_opp:
                warn("W3: verdict=contradicted 但无 direct+opposite 证据")
            if v == "supported" and not has_dir_same:
                warn("W4: verdict=supported 但无 direct+same 证据")
            if v in ("supported", "partially_supported") and not has_pro:
                warn("W6: verdict=%s 但台账完全无 pro 证据" % v)
    return errors, warnings


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="台账 schema 与标注一致性机检（ERROR 阻塞 exit 1，WARNING 仅打印）。")
    ap.add_argument("paths", nargs="+", help="台账 JSON 文件或目录")
    args = ap.parse_args(argv)

    any_err = False
    for path in iter_ledger_paths(args.paths):
        try:
            with open(path, "r", encoding="utf-8") as f:
                ledger = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            print("ERROR: 无法读取 %s: %s" % (path, e), file=sys.stderr)
            return 2
        errors, warnings = validate_ledger(ledger, path)
        for w in warnings:
            print("WARNING [%s] %s" % (os.path.basename(path), w))
        for e_ in errors:
            print("ERROR   [%s] %s" % (os.path.basename(path), e_))
        if errors:
            any_err = True
        if not errors and not warnings:
            print("OK      [%s] 通过（claim_id=%s, 证据 %d 条）" % (
                os.path.basename(path), ledger.get("claim_id"),
                len(ledger.get("evidence", []))))
    return 1 if any_err else 0


if __name__ == "__main__":
    sys.exit(main())
