#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cost_report.py — 运行结束成本报告。

把 ledger.jsonl 折叠成：
  - cost_report.json：逐步骤花费、合计、预算利用率、被跳过项及原因；
  - cost_report.md：中文摘要（利用率百分比、跳过原因），其内容设计为可摘录进
    result.json 的 change_records / uncertainty。

所有数字均从账本重算，绝不信任外部传入的汇总值；账本链损坏 → 退出码 1。
退出码：0 正常；1 违反；2 用法错误。
仅使用 Python 标准库。
"""
import argparse
import datetime
import hashlib
import json
import os
import sys

DIMS = ("requests", "seconds", "tokens")
GENESIS = "0" * 64
DEFAULT_BUDGET = {"requests": 64, "seconds": 900, "tokens": 16384}
DIM_LABEL = {"requests": "模型请求数", "seconds": "秒", "tokens": "token 数"}


def canon(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def load_json_arg(text_or_path):
    if os.path.exists(text_or_path):
        with open(text_or_path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    return json.loads(text_or_path)


def read_and_verify(path):
    lines = []
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as fh:
            for raw in fh:
                raw = raw.strip()
                if raw:
                    lines.append(json.loads(raw))
    prev = GENESIS
    for i, ln in enumerate(lines):
        body = {k: ln[k] for k in ("seq", "ts", "kind", "payload", "prev_hash")}
        if ln.get("seq") != i or ln.get("prev_hash") != prev \
                or ln.get("line_hash") != sha(canon(body)):
            return None, "line %d: sha256 链校验失败" % i
        prev = ln["line_hash"]
    return lines, "ok"


def pct(a, b):
    return round(100.0 * a / b, 2) if b else 0.0


def main(argv=None):
    ap = argparse.ArgumentParser(description="运行结束成本报告")
    ap.add_argument("--ledger", required=True, help="ledger.jsonl")
    ap.add_argument("--budget", help="预算 JSON 字符串或文件（缺省 64/900/16384）")
    ap.add_argument("--out", required=True, help="cost_report.json 输出路径")
    ap.add_argument("--md", required=True, help="cost_report.md 输出路径（中文）")
    args = ap.parse_args(argv)

    try:
        budget = load_json_arg(args.budget) if args.budget else dict(DEFAULT_BUDGET)
    except (ValueError, OSError) as exc:
        print("错误：budget 非法：%s" % exc, file=sys.stderr)
        return 2
    for d in DIMS:
        budget.setdefault(d, DEFAULT_BUDGET[d])

    lines, msg = read_and_verify(args.ledger)
    if lines is None:
        print("违反：账本损坏：%s" % msg, file=sys.stderr)
        return 1

    per_step = {}
    totals = {d: 0 for d in DIMS}
    skipped = []
    degrades = []
    checkpoints = 0
    for ln in lines:
        p = ln["payload"]
        if ln["kind"] == "spend":
            sid = str(p.get("step_id", "__unattributed__"))
            rec = per_step.setdefault(sid, {d: 0 for d in DIMS} | {"events": 0})
            for d in DIMS:
                amt = int(p.get(d, 0))
                rec[d] += amt
                totals[d] += amt
            rec["events"] += 1
        elif ln["kind"] == "plan":
            for s in p.get("skipped", []) or []:
                skipped.append({"id": s.get("id"), "reason": s.get("reason"),
                                "plan_seq": ln["seq"]})
        elif ln["kind"] == "degrade":
            degrades.append({"seq": ln["seq"], "ts": ln["ts"],
                             "payload_summary": p.get("trigger", p.get("reason", ""))})
        elif ln["kind"] == "checkpoint":
            checkpoints += 1

    util = {d: pct(totals[d], budget[d]) for d in DIMS}
    report = {
        "version": 1,
        "generated_at": now_iso(),
        "source": "recomputed-from-ledger",
        "ledger_events": len(lines),
        "ledger_head": lines[-1]["line_hash"] if lines else GENESIS,
        "budget": budget,
        "spent_total": totals,
        "remaining": {d: budget[d] - totals[d] for d in DIMS},
        "utilization_pct": util,
        "per_step": {k: per_step[k] for k in sorted(per_step)},
        "skipped_items": skipped,
        "degrade_events": degrades,
        "checkpoint_events": checkpoints,
    }
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")

    lines_md = [
        "# 成本报告（由预算账本重算）",
        "",
        "- 生成时间：%s" % now_iso(),
        "- 账本事件数：%d；链头：`%s`" % (len(lines), report["ledger_head"][:16] + "…"),
        "- 检查点事件：%d 次；降级事件：%d 次" % (checkpoints, len(degrades)),
        "",
        "## 预算利用率",
        "",
        "| 维度 | 已用 | 预算 | 利用率 |",
        "| --- | --- | --- | --- |",
    ]
    for d in DIMS:
        lines_md.append("| %s | %d | %d | %.2f%% |"
                        % (DIM_LABEL[d], totals[d], budget[d], util[d]))
    lines_md += ["", "## 逐步骤花费", "",
                 "| 步骤 | 请求 | 秒 | token | 事件数 |",
                 "| --- | --- | --- | --- | --- |"]
    for sid in sorted(per_step):
        r = per_step[sid]
        lines_md.append("| %s | %d | %d | %d | %d |"
                        % (sid, r["requests"], r["seconds"], r["tokens"], r["events"]))
    lines_md += ["", "## 被跳过项及原因", ""]
    if skipped:
        for s in skipped:
            lines_md.append("- `%s`：%s" % (s.get("id"), s.get("reason")))
    else:
        lines_md.append("- 无")
    if degrades:
        lines_md += ["", "## 降级事件", ""]
        for g in degrades:
            lines_md.append("- seq=%d（%s）：%s" % (g["seq"], g["ts"], g["payload_summary"]))
    lines_md += [
        "",
        "## 可摘录进 result.json 的表述",
        "",
        "- change_records：本次运行在预算 %s 内执行，利用率 %s。"
        % (json.dumps(budget, ensure_ascii=False),
           json.dumps(util, ensure_ascii=False)),
        "- uncertainty：被跳过核验 %d 项（见上表），其关联结论的证据强度相应下降。"
        % len(skipped),
        "",
    ]
    with open(args.md, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines_md))

    print(json.dumps({"cost_report": args.out, "markdown": args.md,
                      "utilization_pct": util, "skipped": len(skipped)},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
