#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_anchors.py <plans.json> <evidence.jsonl> <out_dir>

校验证据台账中每一条判定的引文锚点：
  - 结构/schema 校验（item_id, category, plan_id, status, quote, basis, note）
  - quote 必须是对应 plan 文本的精确子串（逐字），报告 char 起止偏移与行号
  - status=missing 必须带非空 absence_scope（记录检索范围）
  - quote 长度 ≤ 120 字符
输出 <out_dir>/anchors_verified.json（全部条目+偏移+verification 标志）与
<out_dir>/anchors_rejected.json。存在任何被拒条目时以退出码 2 结束并在 stdout
列出；全部通过则退出码 0。仅标准库，无网络。
"""
import json
import os
import sys

CATEGORIES = ["假设与变量", "对照组", "设备材料", "时间成本",
              "参数范围", "风险与异常", "伦理与安全"]
STATUSES = ["pass", "fail", "missing", "unknown", "not_applicable"]
REQUIRED = ["item_id", "category", "plan_id", "status", "quote", "basis", "note"]
MAX_QUOTE = 120


def usage(msg):
    sys.stderr.write("用法: verify_anchors.py <plans.json> <evidence.jsonl> <out_dir>\n错误: %s\n" % msg)
    sys.exit(1)


def line_of(text, char_pos):
    return text.count("\n", 0, char_pos) + 1


def reject(entry, reasons, lineno):
    return {"lineno": lineno, "entry": entry, "reasons": reasons}


def main():
    if len(sys.argv) != 4:
        usage("需要三个参数：plans.json, evidence.jsonl, out_dir")
    plans_path, ev_path, out_dir = sys.argv[1], sys.argv[2], sys.argv[3]
    for p in (plans_path, ev_path):
        if not os.path.isfile(p):
            sys.stderr.write("错误: 找不到文件: %s\n" % p)
            sys.exit(1)
    with open(plans_path, "r", encoding="utf-8") as f:
        plans = {p["plan_id"]: p for p in json.load(f)["plans"]}
    os.makedirs(out_dir, exist_ok=True)

    verified, rejected = [], []
    with open(ev_path, "r", encoding="utf-8") as f:
        for lineno, raw in enumerate(f, start=1):
            raw = raw.strip()
            if not raw:
                continue
            reasons = []
            try:
                e = json.loads(raw)
            except json.JSONDecodeError as ex:
                rejected.append(reject(raw, ["JSON 解析失败: %s" % ex], lineno))
                continue
            for k in REQUIRED:
                if k not in e:
                    reasons.append("缺少必填字段: %s" % k)
            if reasons:
                rejected.append(reject(e, reasons, lineno))
                continue
            if e["category"] not in CATEGORIES:
                reasons.append("非法 category: %r（合法值: %s）" % (e["category"], "/".join(CATEGORIES)))
            if e["status"] not in STATUSES:
                reasons.append("非法 status: %r（合法值: %s）" % (e["status"], "/".join(STATUSES)))
            if e["plan_id"] not in plans:
                reasons.append("未知 plan_id: %r（可选: %s）" % (e["plan_id"], "/".join(plans)))
            q = e.get("quote", "")
            if not isinstance(q, str) or not q.strip():
                reasons.append("quote 为空或不是字符串")
            elif len(q) > MAX_QUOTE:
                reasons.append("quote 长度 %d 超过上限 %d 字符" % (len(q), MAX_QUOTE))
            if e.get("status") == "missing":
                scope = e.get("absence_scope")
                if not isinstance(scope, str) or not scope.strip():
                    reasons.append("status=missing 必须提供非空 absence_scope（检索范围说明）")
            if reasons:
                rejected.append(reject(e, reasons, lineno))
                continue

            # exact substring anchoring
            text = plans[e["plan_id"]]["text"]
            idx = text.find(q)
            anchor_ok = idx >= 0
            if not anchor_ok:
                rejected.append(reject(e, [
                    "quote 不是 plan %r 文本的精确子串（逐字校验失败）" % e["plan_id"]], lineno))
                continue
            rec = dict(e)
            rec["verification"] = "verified"
            rec["anchor"] = {"char_start": idx, "char_end": idx + len(q),
                             "line_start": line_of(text, idx),
                             "line_end": line_of(text, idx + len(q) - 1)}
            verified.append(rec)

    with open(os.path.join(out_dir, "anchors_verified.json"), "w", encoding="utf-8") as f:
        json.dump({"entries": verified}, f, ensure_ascii=False, indent=2)
    with open(os.path.join(out_dir, "anchors_rejected.json"), "w", encoding="utf-8") as f:
        json.dump({"rejected": rejected}, f, ensure_ascii=False, indent=2)

    if rejected:
        sys.stdout.write("REJECTED %d 条（验证通过 %d 条）：\n" % (len(rejected), len(verified)))
        for r in rejected:
            sys.stdout.write("  行 %d: %s\n" % (r["lineno"], "; ".join(r["reasons"])))
        sys.exit(2)
    sys.stdout.write("OK: 全部 %d 条证据锚定通过。\n" % len(verified))
    sys.exit(0)


if __name__ == "__main__":
    main()
