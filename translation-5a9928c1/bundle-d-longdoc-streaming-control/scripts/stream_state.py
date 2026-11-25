#!/usr/bin/env python3
"""stream_state.py — 续跑状态台账 + 预算记账。

子命令:
  init         --plan plan.json --out state.json
  mark-done    --state state.json --plan plan.json --chunk c001 \
               --translations chunks/c001.translated.json --requests 1 --seconds 25
  list-pending --state state.json [--requests-limit 64 --seconds-limit 900]
  report       --state state.json --out state_report.json

mark-done 校验：块内全部单元已译且 source 哈希与 plan 一致；缺失/篡改 → exit 1。
幂等：同内容重复 mark-done 记 idempotent-skip，不重复计预算。
"""
import argparse, hashlib, json, sys, time
from datetime import datetime, timezone

LIMITS = {"requests": 64, "seconds": 900}

def sha(t):
    return hashlib.sha256(t.encode("utf-8")).hexdigest()

def load(p):
    return json.load(open(p, encoding="utf-8"))

def save(p, d):
    json.dump(d, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def cmd_init(a):
    plan = load(a.plan)
    state = {"version": 1, "plan_sha256": sha(json.dumps(plan["chunks"], ensure_ascii=False)),
             "budget": {"requests_used": 0, "seconds_used": 0.0,
                        "requests_limit": LIMITS["requests"], "seconds_limit": LIMITS["seconds"]},
             "chunks": {c["id"]: {"status": "pending",
                                  "unit_hashes": {u["unit_id"]: u["sha256"] for u in c["units"]},
                                  "translation_sha256": None, "completed_at": None}
                        for c in plan["chunks"]}}
    save(a.out, state)
    print(f"state init: {len(state['chunks'])} chunks pending -> {a.out}")

def cmd_mark_done(a):
    state = load(a.state)
    plan = load(a.plan)
    chunk = next((c for c in plan["chunks"] if c["id"] == a.chunk), None)
    if chunk is None:
        print(f"ERROR: unknown chunk {a.chunk}", file=sys.stderr); sys.exit(2)
    tr = load(a.translations)
    items = tr["segments"] if isinstance(tr, dict) else tr
    by_uid = {it.get("unit_id"): it for it in items}
    st = state["chunks"][a.chunk]
    errors = []
    for uid, uh in st["unit_hashes"].items():
        it = by_uid.get(uid)
        if it is None:
            errors.append(f"missing unit translation: {uid}"); continue
        if sha(it.get("source", "")) != uh:
            errors.append(f"source tampered/stale for {uid}"); continue
        if not it.get("translation", "").strip():
            errors.append(f"empty translation: {uid}"); continue
    if errors:
        for e in errors:
            print(f"REJECT: {e}", file=sys.stderr)
        sys.exit(1)
    tgt_all = "\n".join(by_uid[u]["translation"] for u in st["unit_hashes"])
    new_hash = sha(tgt_all)
    if st["status"] == "done" and st["translation_sha256"] == new_hash:
        print(f"idempotent-skip: {a.chunk} already done with identical content")
        return
    st["status"] = "done"
    st["translation_sha256"] = new_hash
    st["completed_at"] = now()
    state["budget"]["requests_used"] += a.requests
    state["budget"]["seconds_used"] += a.seconds
    save(a.state, state)
    b = state["budget"]
    print(f"mark-done: {a.chunk} ({len(st['unit_hashes'])} units, +{a.requests} req, "
          f"+{a.seconds:.0f}s; budget {b['requests_used']}/{b['requests_limit']} req, "
          f"{b['seconds_used']:.0f}/{b['seconds_limit']} s)")

def cmd_pending(a):
    state = load(a.state)
    pend = [cid for cid, c in state["chunks"].items() if c["status"] != "done"]
    for cid in pend:
        print(cid)
    b = state["budget"]
    req_left = (a.requests_limit or b["requests_limit"]) - b["requests_used"]
    sec_left = (a.seconds_limit or b["seconds_limit"]) - b["seconds_used"]
    print(f"-- {len(state['chunks']) - len(pend)}/{len(state['chunks'])} chunks done; "
          f"pending={len(pend)}; budget left: {req_left} requests, {sec_left:.0f} s",
          file=sys.stderr)
    if pend and (req_left <= 0 or sec_left <= 0):
        print("BUDGET_EXHAUSTED: deliver partial now", file=sys.stderr)
        sys.exit(1)

def cmd_report(a):
    state = load(a.state)
    done = [cid for cid, c in state["chunks"].items() if c["status"] == "done"]
    pend = [cid for cid, c in state["chunks"].items() if c["status"] == "pending"]
    failed = [cid for cid, c in state["chunks"].items() if c["status"] == "failed"]
    rep = {"chunks_total": len(state["chunks"]), "chunks_done": len(done),
           "chunks_pending": pend, "chunks_failed": failed,
           "complete": not pend and not failed, "budget": state["budget"]}
    save(a.out, rep)
    print(f"report: {rep['chunks_done']}/{rep['chunks_total']} done, "
          f"pending={len(pend)}, failed={len(failed)}, complete={rep['complete']} -> {a.out}")

def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("init"); p.add_argument("--plan", required=True); p.add_argument("--out", required=True); p.set_defaults(fn=cmd_init)
    p = sp.add_parser("mark-done"); p.add_argument("--state", required=True); p.add_argument("--plan", required=True)
    p.add_argument("--chunk", required=True); p.add_argument("--translations", required=True)
    p.add_argument("--requests", type=int, default=1); p.add_argument("--seconds", type=float, default=25.0)
    p.set_defaults(fn=cmd_mark_done)
    p = sp.add_parser("list-pending"); p.add_argument("--state", required=True)
    p.add_argument("--requests-limit", type=int); p.add_argument("--seconds-limit", type=int)
    p.set_defaults(fn=cmd_pending)
    p = sp.add_parser("report"); p.add_argument("--state", required=True); p.add_argument("--out", required=True); p.set_defaults(fn=cmd_report)
    a = ap.parse_args(); a.fn(a)

if __name__ == "__main__":
    main()
