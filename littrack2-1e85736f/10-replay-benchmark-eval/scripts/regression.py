#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""regression.py — 两次运行的指标回归对比。

输入：
  --current  本次 metrics.json
  --history  历史运行记录 run_history.json：{"runs": [{"run_id", "metrics", "counts",
             "tp_keys", "fp_keys", "fn_keys"}, ...]}，取最后一个 run 作为基线。

默认回归阈值（依据与调整方式见 references/regression_thresholds.md）：
  recall 下降         > 0.05  -> recall_regression
  false_alert_rate 上升 > 0.05 -> false_alert_regression
  duplicate_rate 上升  > 0.02  -> duplicate_regression
  新增 FN / FP 条目（按 canonical_key 集合差）-> new_false_negatives / new_false_positives

无历史记录时输出 status="no_history"，这不是错误，只是无基线可比。

仅使用 Python3 标准库，完全离线。
"""
import argparse
import json
import sys


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def dump_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")


def main(argv=None):
    ap = argparse.ArgumentParser(description="两次运行的指标回归对比")
    ap.add_argument("--current", required=True, help="本次运行的 metrics.json")
    ap.add_argument("--history", default=None, help="run_history.json（可缺省）")
    ap.add_argument("--out", required=True, help="输出 regression.json 路径")
    ap.add_argument("--recall-drop", type=float, default=0.05)
    ap.add_argument("--far-increase", type=float, default=0.05)
    ap.add_argument("--dup-increase", type=float, default=0.02)
    args = ap.parse_args(argv)

    cur = load_json(args.current)
    thresholds = {"recall_drop": args.recall_drop,
                  "false_alert_rate_increase": args.far_increase,
                  "duplicate_rate_increase": args.dup_increase}

    if not args.history:
        out = {"status": "no_history", "thresholds": thresholds,
               "note": "未提供历史运行记录，无法做回归对比。"}
        dump_json(args.out, out)
        print("regression: no_history")
        return 0

    hist = load_json(args.history)
    runs = hist.get("runs") if isinstance(hist, dict) else None
    if not runs:
        out = {"status": "no_runs", "thresholds": thresholds,
               "note": "历史文件中没有可用的 run 记录。"}
        dump_json(args.out, out)
        print("regression: no_runs")
        return 0

    base = runs[-1]
    deltas = {}
    for k in ("precision", "recall", "duplicate_rate", "false_alert_rate",
              "backfill_misclassification_rate"):
        b = (base.get("metrics") or {}).get(k)
        c = (cur.get("metrics") or {}).get(k)
        if b is not None and c is not None:
            deltas[k] = round(c - b, 6)

    flags = []
    if deltas.get("recall") is not None and deltas["recall"] < -args.recall_drop:
        flags.append({"type": "recall_regression",
                      "detail": "recall %.4f -> %.4f（下降 %.4f，阈值 %.2f）"
                                % (base["metrics"]["recall"], cur["metrics"]["recall"],
                                   -deltas["recall"], args.recall_drop)})
    if deltas.get("false_alert_rate") is not None and deltas["false_alert_rate"] > args.far_increase:
        flags.append({"type": "false_alert_regression",
                      "detail": "false_alert_rate %.4f -> %.4f（上升 %.4f，阈值 %.2f）"
                                % (base["metrics"]["false_alert_rate"],
                                   cur["metrics"]["false_alert_rate"],
                                   deltas["false_alert_rate"], args.far_increase)})
    if deltas.get("duplicate_rate") is not None and deltas["duplicate_rate"] > args.dup_increase:
        flags.append({"type": "duplicate_regression",
                      "detail": "duplicate_rate %.4f -> %.4f（上升 %.4f，阈值 %.2f）"
                                % (base["metrics"]["duplicate_rate"],
                                   cur["metrics"]["duplicate_rate"],
                                   deltas["duplicate_rate"], args.dup_increase)})

    cur_fn, base_fn = set(cur.get("fn_keys") or []), set(base.get("fn_keys") or [])
    cur_fp, base_fp = set(cur.get("fp_keys") or []), set(base.get("fp_keys") or [])
    new_fn = sorted(cur_fn - base_fn)
    new_fp = sorted(cur_fp - base_fp)
    resolved_fn = sorted(base_fn - cur_fn)
    resolved_fp = sorted(base_fp - cur_fp)
    if new_fn:
        flags.append({"type": "new_false_negatives", "detail": "本次新漏报 %d 条: %s" % (len(new_fn), new_fn)})
    if new_fp:
        flags.append({"type": "new_false_positives", "detail": "本次新误报 %d 条: %s" % (len(new_fp), new_fp)})

    out = {
        "status": "compared",
        "baseline_run_id": base.get("run_id"),
        "thresholds": thresholds,
        "baseline_metrics": base.get("metrics"),
        "current_metrics": cur.get("metrics"),
        "deltas": deltas,
        "flags": flags,
        "new_fn_keys": new_fn,
        "new_fp_keys": new_fp,
        "resolved_fn_keys": resolved_fn,
        "resolved_fp_keys": resolved_fp,
        "verdict": "REGRESSION" if flags else "NO_REGRESSION",
    }
    dump_json(args.out, out)
    print("regression: baseline=%s verdict=%s flags=%d" % (base.get("run_id"), out["verdict"], len(flags)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
