#!/usr/bin/env python3
"""assemble_result.py — 合同组装：完整译文 + 双语对照 + 审计结果 + 人工确认清单。"""
import argparse, json, os

def load(p):
    return json.load(open(p, encoding="utf-8"))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True)
    ap.add_argument("--translations", required=True)
    ap.add_argument("--audit", required=True)
    ap.add_argument("--review-md", default=None)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    case = load(a.case)
    tr = load(a.translations)
    audit = load(a.audit)
    items = tr["segments"] if isinstance(tr, dict) else tr
    os.makedirs(a.out, exist_ok=True)

    done = [s for s in items if s.get("translation", "").strip()]
    missing = [s["id"] for s in items if not s.get("translation", "").strip()]
    full_text = "\n\n".join(s["translation"].strip() for s in done)
    hard = sum(audit["summary"].get(k, 0) for k in
               ("missing", "changed", "added", "negation_lost", "qualifier_lost"))
    status = ("success" if (not missing and hard == 0) else
              ("partial" if done else "failed"))

    bilingual = [{"id": s["id"], "source": s.get("source", ""), "target": s.get("translation", "") or None,
                  "issues": next((g["issues"] for g in audit["segments"] if g["id"] == s["id"]), [])}
                 for s in items]
    uncertainties = []
    for g in audit["segments"]:
        for iss in g["issues"]:
            uncertainties.append({"segment": g["id"], **iss})
        for iss in g.get("explained", []):
            uncertainties.append({"segment": g["id"], "explained": True, **iss})
    uncertainties += [{"type": "untranslated_segment", "segment": sid} for sid in missing]

    contract = case.get("output_contract", {})
    required = contract.get("required", [])
    known = {
        "translated_text": full_text,
        "translation": full_text,
        "bilingual": bilingual,
        "bilingual_pairs": bilingual,
        "terminology": tr.get("terminology", []) if isinstance(tr, dict) else [],
        "uncertainties": uncertainties,
        "audit": audit["summary"],
        "fidelity_audit": audit,
        "sources": case.get("source_provenance", {}),
        "exceptions": [{"type": "missing_translation", "segment": sid} for sid in missing],
    }
    payload = {"case_id": case.get("case_id"), "status": status}
    extras = {}
    for k in required:
        if k in ("case_id", "status"):
            continue
        if k in known:
            payload[k] = known[k]
        else:
            payload[k] = known["audit"] if k in ("verification", "quality_check") else \
                         known["sources"] if k in ("evidence", "provenance") else \
                         known["bilingual"] if k in ("alignment", "paragraphs", "segments") else \
                         known["uncertainties"]
            extras[k] = "最佳努力映射"
    if extras:
        payload["extras"] = extras
    payload.setdefault("audit", audit["summary"])
    json.dump(payload, open(os.path.join(a.out, "result.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)

    L = [f"# 双语对照（case={case.get('case_id')}）", ""]
    for b in bilingual:
        L.append(f"## {b['id']}")
        L.append(b["source"])
        L.append("")
        L.append(b["target"] or "⟦未译⟧")
        L.append("")
    open(os.path.join(a.out, "bilingual.md"), "w", encoding="utf-8").write("\n".join(L))
    print(f"result.json + bilingual.md -> {a.out} (status={status}, hard_issues={hard}, "
          f"missing={len(missing)})")

if __name__ == "__main__":
    main()
