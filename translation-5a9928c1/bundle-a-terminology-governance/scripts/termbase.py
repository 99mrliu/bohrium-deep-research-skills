#!/usr/bin/env python3
"""termbase.py — 术语表决议、锁定与校验。

子命令:
  init          --candidates candidates.json --out termbase.json
  decide        --termbase TB --term T (--preferred 译名 | --keep-original)
                  [--sense 备注] [--reason 依据] [--forbid 变体1,变体2] [--abbr AB]
  lock          --termbase TB        # lock = 决议规范化JSON 的 sha256
  verify-lock   --termbase TB        # 锁被破坏 → exit 1 LOCK_BROKEN
  export-glossary --termbase TB --out glossary.md
锁语义: lock 之后任何 decide/undecide 都必须先 unlock（记录原因），审计脚本会拒绝
在锁破坏状态下通过的报告。
"""
import argparse, hashlib, json, sys
from datetime import datetime, timezone

def load(p):
    return json.load(open(p, encoding="utf-8"))

def save(p, d):
    json.dump(d, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

def decisions_of(tb):
    return {t: (e.get("decision") or {}) for t, e in sorted(tb["terms"].items())
            if e.get("decision")}

def lock_hash(tb):
    payload = json.dumps(decisions_of(tb), ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()

def cmd_init(a):
    cands = load(a.candidates)["candidates"]
    tb = {"version": 1, "terms": {}, "history": []}
    for c in cands:
        tb["terms"][c["term"]] = {"abbr": c.get("abbr"), "kind": c["kind"],
                                  "occurrences": c["occurrences"], "rank": c["rank"],
                                  "decision": None, "forbid": []}
    save(a.out, tb)
    print(f"termbase init: {len(tb['terms'])} candidate terms (no decisions yet)")

def cmd_decide(a):
    tb = load(a.termbase)
    if tb.get("lock") and not a.force:
        print("ERROR: termbase is LOCKED; pass --force only with a recorded unlock reason", file=sys.stderr)
        sys.exit(1)
    if a.term not in tb["terms"]:
        tb["terms"][a.term] = {"abbr": a.abbr, "kind": "manual", "occurrences": None,
                               "rank": None, "decision": None, "forbid": []}
    e = tb["terms"][a.term]
    if a.preferred and a.keep_original:
        print("ERROR: choose either --preferred or --keep-original", file=sys.stderr)
        sys.exit(2)
    if a.preferred:
        dec = {"kind": "preferred", "target": a.preferred}
    elif a.keep_original:
        dec = {"kind": "keep_original", "target": a.term}
    else:
        print("ERROR: need --preferred or --keep-original", file=sys.stderr)
        sys.exit(2)
    dec["sense"] = a.sense or ""
    dec["reason"] = a.reason or ""
    dec["decided_by"] = "agent"
    dec["decided_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    e["decision"] = dec
    if a.abbr:
        e["abbr"] = a.abbr
    if a.forbid:
        e["forbid"] = [x.strip() for x in a.forbid.split(",") if x.strip()]
    tb.setdefault("history", []).append({"event": "decide", "term": a.term, "decision": dec,
                                         "after_lock": bool(tb.get("lock"))})
    save(a.termbase, tb)
    print(f"decided: {a.term} -> {dec['target']}" + (" [LOCKED, needs re-lock]" if tb.get("lock") else ""))

def cmd_lock(a):
    tb = load(a.termbase)
    h = lock_hash(tb)
    tb["lock"] = {"sha256": h, "terms_locked": len(decisions_of(tb)),
                  "locked_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    save(a.termbase, tb)
    print(f"LOCKED {tb['lock']['terms_locked']} decisions sha256={h[:16]}…")

def cmd_verify_lock(a):
    tb = load(a.termbase)
    if not tb.get("lock"):
        print("ERROR: termbase not locked yet", file=sys.stderr)
        sys.exit(2)
    if lock_hash(tb) != tb["lock"]["sha256"]:
        print("LOCK_BROKEN: decisions changed after lock", file=sys.stderr)
        sys.exit(1)
    print(f"LOCK_OK sha256={tb['lock']['sha256'][:16]}…")

def cmd_export(a):
    tb = load(a.termbase)
    lines = ["# Locked Glossary（锁定术语表，翻译时必须执行）", ""]
    for t, e in sorted(tb["terms"].items()):
        d = e.get("decision")
        if not d:
            continue
        ab = f"（缩写 {e['abbr']}）" if e.get("abbr") else ""
        sense = f"；义项：{d['sense']}" if d.get("sense") else ""
        forbid = f"；禁用变体：{'、'.join(e['forbid'])}" if e.get("forbid") else ""
        lines.append(f"- **{t}**{ab} → {d['target']}{sense}{forbid}")
    lines.append("")
    lines.append("规则：同一义项全篇同一译名；标题/摘要/正文/图注/结论一致；"
                 "禁用变体出现即违规；keep_original 条目允许零译名。")
    open(a.out, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print(f"glossary -> {a.out} ({len(lines)-3} locked terms)")

def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("init"); p.add_argument("--candidates", required=True); p.add_argument("--out", required=True); p.set_defaults(fn=cmd_init)
    p = sp.add_parser("decide"); p.add_argument("--termbase", required=True); p.add_argument("--term", required=True)
    p.add_argument("--preferred"); p.add_argument("--keep-original", action="store_true")
    p.add_argument("--sense"); p.add_argument("--reason"); p.add_argument("--forbid"); p.add_argument("--abbr")
    p.add_argument("--force", action="store_true"); p.set_defaults(fn=cmd_decide)
    p = sp.add_parser("lock"); p.add_argument("--termbase", required=True); p.set_defaults(fn=cmd_lock)
    p = sp.add_parser("verify-lock"); p.add_argument("--termbase", required=True); p.set_defaults(fn=cmd_verify_lock)
    p = sp.add_parser("export-glossary"); p.add_argument("--termbase", required=True); p.add_argument("--out", required=True); p.set_defaults(fn=cmd_export)
    a = ap.parse_args()
    a.fn(a)

if __name__ == "__main__":
    main()
