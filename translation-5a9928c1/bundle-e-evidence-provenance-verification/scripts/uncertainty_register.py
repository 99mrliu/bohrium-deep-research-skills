#!/usr/bin/env python3
"""uncertainty_register.py — 不确定性登记 + 诚实状态推导。

用法: uncertainty_register.py --translations TR.json --evidence evidence_map.json --out register.json
状态推导:
  success: 全部段已译 + 全部证据 verified + 无 gap + 无未决不确定性
  partial: 其余有实质产出的情形（列出全部原因）
  failed:  无一段译文
uncertainty 类型: ambiguous_term | unreadable | unresolved_reference |
                  unverified_evidence | coverage_gap | untranslated_segment | 自定义
"""
import argparse, json

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--translations", required=True)
    ap.add_argument("--evidence", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    tr = json.load(open(a.translations, encoding="utf-8"))
    items = tr["segments"] if isinstance(tr, dict) else tr
    ev = json.load(open(a.evidence, encoding="utf-8"))

    register = []
    ev_by_id = {s["id"]: s for s in ev["segments"]}
    for it in items:
        sid = it.get("id")
        if not it.get("translation", "").strip():
            register.append({"segment": sid, "type": "untranslated_segment",
                             "detail": "段落未译", "blocks_success": True})
            continue
        e = ev_by_id.get(sid, {})
        if e.get("verdict") and e["verdict"] != "verified":
            register.append({"segment": sid, "type": "unverified_evidence",
                             "detail": f"证据核验失败: {e['verdict']}", "blocks_success": True})
        u = it.get("uncertainty")
        if u:
            register.append({"segment": sid, **u, "blocks_success": True})
        elif (it.get("evidence") or {}).get("basis") == "uncertain":
            register.append({"segment": sid, "type": "uncertain_basis",
                             "detail": (it["evidence"].get("note") or "译法存疑，需人工确认"),
                             "blocks_success": True})
    for g in ev["coverage"]["gaps"]:
        register.append({"segment": None, "type": "coverage_gap",
                         "detail": f"源文本 [{g['span'][0]},{g['span'][1]}) 未被任何证据覆盖: {g['preview']}",
                         "blocks_success": True})
    for o in ev["coverage"]["overlaps"]:
        register.append({"segment": None, "type": "overlapping_evidence",
                         "detail": f"证据区间重叠 {o['segments']} @ {o['span']}",
                         "blocks_success": False})

    n_translated = sum(1 for it in items if it.get("translation", "").strip())
    blocking = [r for r in register if r.get("blocks_success")]
    if n_translated == 0:
        status = "failed"
    elif blocking:
        status = "partial"
    else:
        status = "success"
    out = {"status": status, "n_segments": len(items), "n_translated": n_translated,
           "n_uncertainties": len(register), "blocking": len(blocking),
           "register": register}
    json.dump(out, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"register: status={status}, uncertainties={len(register)} "
          f"(blocking={len(blocking)}) -> {a.out}")

if __name__ == "__main__":
    main()
