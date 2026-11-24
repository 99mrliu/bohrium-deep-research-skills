#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pipeline.py — 一键确定性清洗管道（Python 3 标准库）。

为 900 秒/64 请求的 harness 预算设计：**一次命令**跑完全部机械工序，
Agent 只读一份 <2KB 的 digest。七道工序，每道落检查点，崩溃后 --resume
从断点续跑，重复执行幂等（同输入同输出）。

工序：load → sentinel(缺失分类标记) → units(显式倍率换算) → dedup(归一化
主键) → bounds(物理界标记) → report(数字重算) → contract(result.json 填充)

配置 rules.json（Agent 读完字典/工单后编写，是唯一需要判断的产物）：
{
  "input": "/path/table.csv", "encoding": "utf-8-sig",
  "key_columns": ["sample_id","metric"],
  "case_id": "...", "contract_scaffold": {"field1": "", "field2": 0},
  "missing": {"policy": "mark|empty",
              "tokens": {"-999": "entry_missing", "ND": "not_detected"}},
  "units": [{"field": "value", "from_column": "unit",
             "map": {"μg/L": ["mg/L", 0.001]}}],
  "bounds": [{"field": "value", "by_column": "metric",
              "map": {"溶解氧": [0, 20], "总磷": [0, 5]}}],
  "dedup": {"keep": "most_complete"}
}
铁律：只执行配置显式声明的处置；绝不插补；冲突行全部保留进 review_queue。
退出码：0 完成；2 参数/配置错误；6 运行硬错误（已落检查点可续跑）。
"""
import argparse
import csv
import decimal
import hashlib
import json
import os
import re
import sys
import time

decimal.getcontext().prec = 40

STAGES = ["load", "sentinel", "units", "dedup", "bounds", "report", "contract"]
RE_NUM = re.compile(r"^[+-]?\d+(\.\d+)?([eE][+-]?\d+)?$")


def sha256_file(p):
    with open(p, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def norm_key(s):
    return re.sub(r"\s+", " ", s.strip()).casefold()


def fmt_num(x):
    return str(int(x)) if x == int(x) and abs(x) < 1e15 else repr(x)


def fmt_dec(d):
    """Decimal → 最短无噪声十进制文本（去尾零、不丢精度、不用科学计数法）。"""
    if d == d.to_integral_value():
        return str(int(d))
    s = format(d.normalize(), "f")
    return s


class Pipe:
    def __init__(self, rules, workdir, outdir, resume=False):
        self.r = rules
        self.workdir, self.outdir = workdir, outdir
        self.ckpt_dir = os.path.join(workdir, "checkpoints")
        os.makedirs(self.ckpt_dir, exist_ok=True)
        os.makedirs(outdir, exist_ok=True)
        self.state = {}
        self.done = set()
        if resume:
            for s in STAGES:
                p = os.path.join(self.ckpt_dir, "%s.json" % s)
                if os.path.isfile(p):
                    self.done.add(s)
            sp = os.path.join(self.ckpt_dir, "state.json")
            if os.path.isfile(sp):
                self.state = json.load(open(sp, encoding="utf-8"))
        self.log = []

    def checkpoint(self, stage):
        with open(os.path.join(self.ckpt_dir, "%s.json" % stage), "w") as f:
            json.dump({"stage": stage, "ts": round(time.time(), 3)}, f)
        with open(os.path.join(self.ckpt_dir, "state.json"), "w",
                  encoding="utf-8") as f:
            json.dump(self.state, f, ensure_ascii=False)

    def skip(self, stage):
        return stage in self.done

    # ---- 工序 ----
    def load(self):
        src = self.r["input"]
        enc = self.r.get("encoding", "utf-8-sig")
        with open(src, encoding=enc, newline="") as f:
            rows = list(csv.reader(f))
        if not rows:
            raise RuntimeError("空表")
        self.state = {"header": rows[0], "data": rows[1:], "ledger": [],
                      "review": [], "input_sha256": sha256_file(src),
                      "input_path": os.path.abspath(src)}

    def sentinel(self):
        miss = self.r.get("missing") or {}
        tokens = miss.get("tokens") or {}
        policy = miss.get("policy", "mark")
        h = self.state["header"]
        n = 0
        for i, row in enumerate(self.state["data"], 2):
            for j in range(len(row)):
                t = row[j].strip()
                if t in tokens:
                    cls = tokens[t]
                    n += 1
                    if policy == "empty":
                        self.state["ledger"].append(
                            [i, h[j], "missing_to_empty", row[j], "",
                             "missing:%s" % cls, "rules.json"])
                        row[j] = ""
                    else:
                        self.state["ledger"].append(
                            [i, h[j], "missing_marked", row[j], row[j],
                             "missing:%s" % cls, "rules.json"])
        self.state["n_missing"] = n

    def units(self):
        h = self.state["header"]
        idx = {n: j for j, n in enumerate(h)}
        miss_tokens = set(((self.r.get("missing") or {}).get("tokens") or {}).keys())
        n = 0
        for u in self.r.get("units") or []:
            j = idx[u["field"]]
            jc = idx.get(u.get("from_column") or "")
            for i, row in enumerate(self.state["data"], 2):
                t = row[j].strip()
                if not RE_NUM.match(t) or t in miss_tokens:
                    continue  # 哨兵码是缺失标记，不是数值
                u_in = row[jc].strip() if jc is not None else None
                spec = (u.get("map") or {}).get(u_in)
                if not spec:
                    continue
                canon, factor = spec[0], spec[1]
                try:
                    x = decimal.Decimal(t)
                    fdec = decimal.Decimal(str(factor))
                    y = x * fdec
                    if y / fdec != x:
                        raise decimal.InvalidOperation("inverse check failed")
                except (decimal.InvalidOperation, decimal.DivisionByZero,
                        ValueError):
                    self.state["review"].append([i, u["field"], t, "换算不可逆，保留原值"])
                    continue
                self.state["ledger"].append(
                    [i, u["field"], "unit_converted", t, fmt_dec(y),
                     "%s->%s (x%s)" % (u_in, canon, factor), "rules.json"])
                row[j] = fmt_dec(y)
                if jc is not None:
                    self.state["ledger"].append(
                        [i, u["from_column"], "unit_label_updated",
                         row[jc], canon, "follow %s" % u["field"], "rules.json"])
                    row[jc] = canon
                n += 1
        self.state["n_units"] = n

    def dedup(self):
        kc = self.r.get("key_columns") or []
        if not kc:
            self.state["n_dedup"] = 0
            return
        h = self.state["header"]
        idx = {n: j for j, n in enumerate(h)}
        keyset = {idx[k] for k in kc}
        groups = {}
        for i, row in enumerate(self.state["data"]):
            key = "␟".join(norm_key(row[idx[k]]) for k in kc)
            groups.setdefault(key, []).append(i)
        keep, drops = set(), 0
        for key, members in groups.items():
            nonkey = {tuple(v for j, v in enumerate(self.state["data"][i])
                            if j not in keyset) for i in members}
            if len(nonkey) > 1:
                for i in members:
                    keep.add(i)
                    self.state["review"].append(
                        [i + 2, "/".join(kc), key, "主键冲突：全部保留待复核"])
                continue
            winner = max(members, key=lambda i: (
                sum(1 for c in self.state["data"][i] if c.strip()), -i))
            for i in members:
                if i == winner:
                    keep.add(i)
                else:
                    drops += 1
                    self.state["ledger"].append(
                        [i + 2, "/".join(kc), "dedup_drop",
                         json.dumps(self.state["data"][i], ensure_ascii=False),
                         "", "dedup:most_complete", "rules.json"])
        self.state["data"] = [r for i, r in enumerate(self.state["data"])
                              if i in keep]
        self.state["n_dedup"] = drops

    def bounds(self):
        h = self.state["header"]
        idx = {n: j for j, n in enumerate(h)}
        miss_tokens = set(((self.r.get("missing") or {}).get("tokens") or {}).keys())
        n = 0
        for b in self.r.get("bounds") or []:
            j = idx[b["field"]]
            jb = idx.get(b.get("by_column") or "")
            for i, row in enumerate(self.state["data"], 2):
                t = row[j].strip()
                if not RE_NUM.match(t) or t in miss_tokens:
                    continue  # 哨兵码不参与物理界判定
                spec = (b.get("map") or {}).get(row[jb].strip()) \
                    if jb is not None else b.get("range")
                if not spec:
                    continue
                lo, hi = spec
                x = float(t)
                if (lo is not None and x < lo) or (hi is not None and x > hi):
                    n += 1
                    self.state["ledger"].append(
                        [i, b["field"], "out_of_bounds_flag", t, t,
                         "bounds:[%s,%s]" % (lo, hi), "rules.json"])
        self.state["n_bounds"] = n

    def report(self):
        h, data = self.state["header"], self.state["data"]
        ledger = self.state["ledger"]
        actions = {}
        for r in ledger:
            actions[r[2]] = actions.get(r[2], 0) + 1
        rep = {"table": {"rows_out": len(data), "cols": len(h),
                         "input_sha256": self.state["input_sha256"]},
               "counts": {"missing_marked": self.state.get("n_missing", 0),
                          "units_converted": self.state.get("n_units", 0),
                          "dedup_dropped": self.state.get("n_dedup", 0),
                          "out_of_bounds": self.state.get("n_bounds", 0),
                          "review_queue": len(self.state["review"])},
               "actions": actions, "ledger_entries": len(ledger)}
        self.state["report"] = rep

    def contract(self):
        # 写 cleaned/ledger/review/quality_report + result.json
        h = self.state["header"]
        with open(os.path.join(self.outdir, "cleaned.csv"), "w",
                  encoding="utf-8", newline="") as f:
            w = csv.writer(f, lineterminator="\n")
            w.writerow(h)
            w.writerows(self.state["data"])
        with open(os.path.join(self.outdir, "ledger.csv"), "w",
                  encoding="utf-8", newline="") as f:
            w = csv.writer(f, lineterminator="\n")
            w.writerow(["row", "field", "action", "old", "new", "rule", "source"])
            w.writerows(self.state["ledger"])
        with open(os.path.join(self.outdir, "review_queue.csv"), "w",
                  encoding="utf-8", newline="") as f:
            w = csv.writer(f, lineterminator="\n")
            w.writerow(["row", "field", "value", "reason"])
            w.writerows(self.state["review"])
        with open(os.path.join(self.outdir, "quality_report.json"), "w",
                  encoding="utf-8") as f:
            json.dump(self.state["report"], f, ensure_ascii=False, indent=2)
        scaf = self.r.get("contract_scaffold") or {}
        result = {"case_id": self.r.get("case_id", "UNKNOWN_CASE_ID")}
        for k, v in scaf.items():
            result[k] = v
        counts = self.state["report"]["counts"]
        result.setdefault("summary", counts)
        if result.get("summary") != counts and isinstance(
                result.get("summary"), dict):
            merged = dict(counts)
            merged.update(result["summary"])
            result["summary"] = merged
        result["status"] = "partial" if self.state["review"] else "success"
        result.setdefault("artifacts", ["cleaned.csv", "ledger.csv",
                                        "quality_report.json",
                                        "review_queue.csv"])
        with open(os.path.join(self.outdir, "result.json"), "w",
                  encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

    def run(self):
        for s in STAGES:
            if self.skip(s):
                self.log.append("skip %s (checkpoint)" % s)
                continue
            getattr(self, s)()
            self.checkpoint(s)
            self.log.append("done %s" % s)
        return self.log


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rules", required=True, help="rules.json")
    ap.add_argument("--workdir", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--resume", action="store_true", help="从检查点续跑")
    args = ap.parse_args()
    try:
        rules = json.load(open(args.rules, encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print("ERROR: rules.json 不可读: %s" % e, file=sys.stderr)
        sys.exit(2)
    if not os.path.isfile(rules.get("input", "")):
        print("ERROR: 输入表不存在: %s" % rules.get("input"), file=sys.stderr)
        sys.exit(2)
    pipe = Pipe(rules, args.workdir, args.outdir, resume=args.resume)
    try:
        log = pipe.run()
    except Exception as e:
        print("ERROR: 工序中断（可 --resume 续跑）: %s" % e, file=sys.stderr)
        sys.exit(6)
    counts = pipe.state.get("report", {}).get("counts", {})
    digest = {"status": "ok", "log": log, "counts": counts,
              "rows_out": len(pipe.state.get("data", [])),
              "ledger_entries": len(pipe.state.get("ledger", [])),
              "review_queue": len(pipe.state.get("review", [])),
              "result": os.path.join(os.path.abspath(args.outdir), "result.json")}
    print(json.dumps(digest, ensure_ascii=False))


if __name__ == "__main__":
    main()
