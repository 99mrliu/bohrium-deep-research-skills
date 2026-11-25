#!/usr/bin/env python3
"""assemble_result.py — 按台账与计划组装合同交付（已完块按序拼接，未译块不伪造）。"""
import argparse, json, os

def load(p):
    return json.load(open(p, encoding="utf-8"))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True)
    ap.add_argument("--plan", required=True)
    ap.add_argument("--state", required=True)
    ap.add_argument("--translations-dir", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    case = load(a.case)
    plan = load(a.plan)
    state = load(a.state)
    os.makedirs(a.out, exist_ok=True)

    unit_tr = {}
    for cid, st in state["chunks"].items():
        if st["status"] != "done":
            continue
        fp = os.path.join(a.translations_dir, f"{cid}.translated.json")
        if not os.path.exists(fp):
            continue
        tr = load(fp)
        items = tr["segments"] if isinstance(tr, dict) else tr
        for it in items:
            unit_tr[it["unit_id"]] = it

    bilingual, full_texts, missing_units = [], [], []
    for c in plan["chunks"]:
        for u in c["units"]:
            it = unit_tr.get(u["unit_id"])
            tgt = it.get("translation", "") if it else ""
            bilingual.append({"id": u["unit_id"], "chunk": c["id"], "kind": u["kind"],
                              "source": u["text"], "target": tgt or None,
                              "anchor": f"{u['unit_id']}@{c['id']}"})
            if tgt.strip():
                full_texts.append(tgt.strip())
            else:
                missing_units.append(u["unit_id"])
    done_units = len(full_texts)
    total_units = len(bilingual)
    b = state["budget"]
    status = ("success" if not missing_units else
              ("partial" if done_units else "failed"))
    uncertainties = ([{"type": "untranslated_unit", "unit": u} for u in missing_units]
                     + [{"type": "budget", **b}])

    contract = case.get("output_contract", {})
    required = contract.get("required", [])
    known = {
        "translated_text": "\n\n".join(full_texts),
        "translation": "\n\n".join(full_texts),
        "bilingual": bilingual,
        "bilingual_pairs": bilingual,
        "alignment": bilingual,
        "uncertainties": uncertainties,
        "coverage": {"units_done": done_units, "units_total": total_units,
                     "chunks_done": sum(1 for s in state["chunks"].values() if s["status"] == "done"),
                     "chunks_total": len(state["chunks"])},
        "state_report": {"budget": b, "missing_units": missing_units},
        "sources": case.get("source_provenance", {}),
        "exceptions": [{"type": "untranslated_unit", "unit": u} for u in missing_units],
    }
    payload = {"case_id": case.get("case_id"), "status": status}
    extras = {}
    for k in required:
        if k in ("case_id", "status"):
            continue
        if k in known:
            payload[k] = known[k]
        else:
            payload[k] = known["coverage"] if k in ("completeness", "coverage") else \
                         known["sources"] if k in ("evidence", "provenance") else \
                         known["bilingual"]
            extras[k] = "最佳努力映射"
    if extras:
        payload["extras"] = extras
    payload.setdefault("coverage", known["coverage"])
    json.dump(payload, open(os.path.join(a.out, "result.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)

    L = [f"# 双语对照（case={case.get('case_id')}）", "",
         f"单元 {done_units}/{total_units}；状态 {status}", ""]
    for bl in bilingual:
        L.append(f"## {bl['id']} [{bl['kind']}, 块 {bl['chunk']}]")
        L.append(bl["source"])
        L.append("")
        L.append(bl["target"] or "⟦未译⟧")
        L.append("")
    open(os.path.join(a.out, "bilingual.md"), "w", encoding="utf-8").write("\n".join(L))
    print(f"result.json + bilingual.md -> {a.out} (status={status}, units {done_units}/{total_units})")

if __name__ == "__main__":
    main()
