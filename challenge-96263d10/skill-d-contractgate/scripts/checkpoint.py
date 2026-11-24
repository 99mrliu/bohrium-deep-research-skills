#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""checkpoint.py -- 阶段打卡：每个阶段结束都留下可交付状态与固证。

- 追加 journal.jsonl（谁、何时、干了什么、带哪些产物哈希）；
- 把登记产物（--artifact）以 sha256 同步进 result.json 的 artifacts；
- 更新 run_state.json 的阶段梯子与 result.json 的 last_checkpoint。
设计意图：900 秒预算内任何时刻被打断，/app/output 都是一份自洽的 partial。

用法:
  python3 checkpoint.py --work /app/work --output /app/output \
      --stage spec-extract --note "模板实测完成" \
      --artifact /app/output/spec.json [--artifact ...]
退出码: 0 正常; 2 产物路径不存在（拒绝登记幽灵产物）。
"""
import argparse, hashlib, json, os, sys, time

def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--output", default="/app/output")
    ap.add_argument("--stage", required=True)
    ap.add_argument("--note", default="")
    ap.add_argument("--artifact", action="append", default=[])
    a = ap.parse_args()

    arts = []
    for p in a.artifact:
        if not os.path.isfile(p):
            print("ERROR: 产物不存在，拒绝登记: %s" % p, file=sys.stderr)
            sys.exit(2)
        arts.append({"path": p, "sha256": sha256_of(p), "size": os.path.getsize(p)})

    now = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    entry = {"time": now, "stage": a.stage, "note": a.note,
             "artifacts": [{"path": x["path"], "sha256": x["sha256"]} for x in arts]}
    with open(os.path.join(a.work, "journal.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    state_path = os.path.join(a.work, "run_state.json")
    state = json.load(open(state_path, encoding="utf-8")) if os.path.isfile(state_path) \
        else {"stages": []}
    state["stages"].append({"name": a.stage, "status": "done", "time": now, "note": a.note})
    json.dump(state, open(state_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    rj_path = os.path.join(a.output, "result.json")
    if os.path.isfile(rj_path):
        rj = json.load(open(rj_path, encoding="utf-8"))
        have = {x["path"] for x in rj.get("artifacts", [])}
        rj.setdefault("artifacts", [])
        for x in arts:
            if x["path"] not in have:
                rj["artifacts"].append(x)
        rj["last_checkpoint"] = now
        if "run started; contract fields pending" in rj.get("limits", []) and a.stage != "probe":
            rj["limits"] = [x for x in rj["limits"] if x != "run started; contract fields pending"]
        json.dump(rj, open(rj_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("checkpoint stage=%s artifacts=%d -> journal.jsonl, run_state.json, result.json" % (
        a.stage, len(arts)))

if __name__ == "__main__":
    main()
