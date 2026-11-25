#!/usr/bin/env python3
"""coverage.py — 覆盖台账：不漏段、不重段、不错位。

子命令:
  init          --segments segments.json --out ledger.json
  apply         --ledger ledger.json --translations translations.json
  list-pending  --ledger ledger.json
  report        --ledger ledger.json --out coverage_report.json

apply 的拒绝条件（exit 1，写明原因）:
  * 未知 ID；* 同一文件内重复 ID；* source 与台账 sha256 不符（错位/陈旧）。
成功回填后块 status=done 并记录 translation_sha256；幂等（重复 apply 同内容跳过）。
"""
import argparse, hashlib, json, sys

def sha(t):
    return hashlib.sha256(t.encode("utf-8")).hexdigest()

def load(p):
    return json.load(open(p, encoding="utf-8"))

def save(p, d):
    json.dump(d, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

def cmd_init(a):
    segs = load(a.segments)["segments"]
    ledger = {"version": 1,
              "blocks": [{"id": s["id"], "kind": s["kind"], "page": s["page"],
                          "source_sha256": s["sha256"], "status": "pending",
                          "translation_sha256": None} for s in segs]}
    save(a.out, ledger)
    print(f"ledger init: {len(ledger['blocks'])} blocks pending -> {a.out}")

def cmd_apply(a):
    ledger = load(a.ledger)
    tr = load(a.translations)
    items = tr["segments"] if isinstance(tr, dict) else tr
    by_id = {}
    errors = []
    for it in items:
        sid = it.get("id")
        if not sid:
            errors.append("entry without id"); continue
        if sid in by_id:
            errors.append(f"duplicate id in translations: {sid}"); continue
        by_id[sid] = it
    known = {b["id"]: b for b in ledger["blocks"]}
    applied, skipped = 0, 0
    for sid, it in by_id.items():
        if sid not in known:
            errors.append(f"unknown id: {sid}"); continue
        blk = known[sid]
        if sha(it.get("source", "")) != blk["source_sha256"]:
            errors.append(f"source mismatch (misalignment/stale): {sid}"); continue
        tgt = it.get("translation", "")
        if not tgt.strip():
            errors.append(f"empty translation: {sid}"); continue
        new_hash = sha(tgt)
        if blk["status"] == "done" and blk["translation_sha256"] == new_hash:
            skipped += 1; continue
        blk["status"] = "done"
        blk["translation_sha256"] = new_hash
        applied += 1
    save(a.ledger, ledger)
    if errors:
        for e in errors:
            print(f"REJECT: {e}", file=sys.stderr)
        print(f"apply: {applied} applied, {skipped} idempotent-skip, {len(errors)} rejected -> {a.ledger}", file=sys.stderr)
        sys.exit(1)
    print(f"apply: {applied} applied, {skipped} idempotent-skip -> {a.ledger}")

def cmd_pending(a):
    ledger = load(a.ledger)
    pend = [b for b in ledger["blocks"] if b["status"] != "done"]
    done = len(ledger["blocks"]) - len(pend)
    for b in pend:
        print(f"{b['id']} ({b['kind']}, page {b['page']})")
    print(f"-- {done}/{len(ledger['blocks'])} done, {len(pend)} pending", file=sys.stderr)

def cmd_report(a):
    ledger = load(a.ledger)
    blocks = ledger["blocks"]
    done = [b for b in blocks if b["status"] == "done"]
    missing = [b["id"] for b in blocks if b["status"] != "done"]
    # 乱序检查：ledger 按 id 升序即源序；重复 id 不可能（init 保证），这里再防御一次
    ids = [b["id"] for b in blocks]
    dups = sorted({i for i in ids if ids.count(i) > 1})
    rep = {"total_blocks": len(blocks), "translated": len(done),
           "missing": missing, "duplicate_ids": dups,
           "complete": (not missing and not dups),
           "by_kind": {}}
    for b in blocks:
        k = b["kind"]
        rep["by_kind"].setdefault(k, {"total": 0, "done": 0})
        rep["by_kind"][k]["total"] += 1
        rep["by_kind"][k]["done"] += 1 if b["status"] == "done" else 0
    save(a.out, rep)
    print(f"coverage: {rep['translated']}/{rep['total_blocks']} blocks, "
          f"missing={len(missing)}, dups={len(dups)}, complete={rep['complete']} -> {a.out}")
    sys.exit(0 if rep["complete"] else 1)

def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("init"); p.add_argument("--segments", required=True); p.add_argument("--out", required=True); p.set_defaults(fn=cmd_init)
    p = sp.add_parser("apply"); p.add_argument("--ledger", required=True); p.add_argument("--translations", required=True); p.set_defaults(fn=cmd_apply)
    p = sp.add_parser("list-pending"); p.add_argument("--ledger", required=True); p.set_defaults(fn=cmd_pending)
    p = sp.add_parser("report"); p.add_argument("--ledger", required=True); p.add_argument("--out", required=True); p.set_defaults(fn=cmd_report)
    a = ap.parse_args(); a.fn(a)

if __name__ == "__main__":
    main()
