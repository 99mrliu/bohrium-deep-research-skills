#!/usr/bin/env python3
"""assemble_result.py — 合同组装：完整译文 + 双语对照 + 证据/不确定性（诚实状态）。"""
import argparse, json, os

def load(p):
    return json.load(open(p, encoding="utf-8"))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True)
    ap.add_argument("--translations", required=True)
    ap.add_argument("--evidence", required=True)
    ap.add_argument("--register", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    case = load(a.case)
    tr = load(a.translations)
    ev = load(a.evidence)
    reg = load(a.register)
    items = tr["segments"] if isinstance(tr, dict) else tr
    os.makedirs(a.out, exist_ok=True)

    done = [s for s in items if s.get("translation", "").strip()]
    full_text = "\n\n".join(s["translation"].strip() for s in done)
    ev_by_id = {s["id"]: s for s in ev["segments"]}
    bilingual = []
    for s in items:
        e = ev_by_id.get(s["id"], {})
        bilingual.append({"id": s["id"], "source": s.get("source", ""),
                          "target": s.get("translation", "") or None,
                          "evidence": {"quote": (s.get("evidence") or {}).get("quote"),
                                       "offset": e.get("resolved_start"),
                                       "verdict": e.get("verdict")},
                          "basis": (s.get("evidence") or {}).get("basis"),
                          "note": (s.get("evidence") or {}).get("note")})
    uncertainties = [{"segment": r.get("segment"), "type": r.get("type"),
                      "detail": r.get("detail")} for r in reg["register"]]
    status = reg["status"]

    contract = case.get("output_contract", {})
    required = contract.get("required", [])
    known = {
        "translated_text": full_text,
        "translation": full_text,
        "bilingual": bilingual,
        "bilingual_pairs": bilingual,
        "alignment": bilingual,
        "terminology": tr.get("terminology", []) if isinstance(tr, dict) else [],
        "uncertainties": uncertainties,
        "evidence_map": {"counts": ev["counts"],
                         "coverage": {"gaps": len(ev["coverage"]["gaps"]),
                                      "overlaps": len(ev["coverage"]["overlaps"]),
                                      "covered_chars": ev["coverage"]["covered_chars"],
                                      "source_chars": ev["source_chars"]}},
        "verification": {"status": status, "register": reg["register"]},
        "sources": case.get("source_provenance", {}),
        "exceptions": uncertainties,
    }
    payload = {"case_id": case.get("case_id"), "status": status}
    extras = {}
    for k in required:
        if k in ("case_id", "status"):
            continue
        if k in known:
            payload[k] = known[k]
        else:
            payload[k] = known["evidence_map"] if k in ("coverage", "provenance_map") else \
                         known["sources"] if k in ("evidence", "provenance") else \
                         known["bilingual"] if k in ("paragraphs", "segments") else \
                         known["uncertainties"]
            extras[k] = "最佳努力映射"
    if extras:
        payload["extras"] = extras
    payload.setdefault("evidence_map", known["evidence_map"])
    payload.setdefault("verification", known["verification"])
    json.dump(payload, open(os.path.join(a.out, "result.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)

    L = [f"# 双语对照（case={case.get('case_id')}）", ""]
    for b in bilingual:
        L.append(f"## {b['id']} [verdict={b['evidence']['verdict']}, basis={b['basis']}]")
        L.append(b["source"])
        L.append("")
        L.append(b["target"] or "⟦未译⟧")
        L.append("")
    open(os.path.join(a.out, "bilingual.md"), "w", encoding="utf-8").write("\n".join(L))
    print(f"result.json + bilingual.md -> {a.out} (status={status}, "
          f"uncertainties={len(uncertainties)})")

if __name__ == "__main__":
    main()
