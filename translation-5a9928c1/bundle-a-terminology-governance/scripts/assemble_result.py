#!/usr/bin/env python3
"""assemble_result.py — 按实际 output_contract 组装 result.json + bilingual.md。

用法: assemble_result.py --case /input/case.json --translations TR \
        --termbase TB --violations V --out /app/output
规则: 完整译文进文本字段（非路径）；合同未知字段给最佳努力结构化值并记入
extras.unmapped；所有段落缺失翻译 → status=partial；附 sources/audit。
"""
import argparse, hashlib, json, os

def load(p):
    return json.load(open(p, encoding="utf-8"))

def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True)
    ap.add_argument("--translations", required=True)
    ap.add_argument("--termbase", required=True)
    ap.add_argument("--violations", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    case = load(a.case)
    tr = load(a.translations)
    segs = tr["segments"] if isinstance(tr, dict) else tr
    tb = load(a.termbase)
    vio = load(a.violations)
    os.makedirs(a.out, exist_ok=True)

    done = [s for s in segs if s.get("translation", "").strip()]
    missing = [s["id"] for s in segs if not s.get("translation", "").strip()]
    full_text = "\n\n".join(s["translation"].strip() for s in done)
    bilingual = [{"id": s["id"], "source": s["original"], "target": s.get("translation", "") or None,
                  "zone": s.get("zone", "body")} for s in segs]
    terminology = [{"term": t, "abbr": e.get("abbr"), "decision": e["decision"], "forbid": e.get("forbid", [])}
                   for t, e in sorted(tb["terms"].items()) if e.get("decision")]
    uncertainties = ([{"type": h["class"], "term": h["term"], "detail": h["detail"]} for h in vio["human_confirm"]]
                     + [{"type": "untranslated_segment", "segment": sid, "detail": "段落未译"}
                        for sid in missing])

    status = "success" if (not missing and not vio["violations"]) else \
             ("partial" if done else "failed")

    contract = case.get("output_contract", {})
    required = contract.get("required", [])
    payload = {"case_id": case.get("case_id"), "status": status}
    known = {
        "translated_text": full_text,
        "translation": full_text,
        "bilingual": bilingual,
        "bilingual_pairs": bilingual,
        "terminology": terminology,
        "glossary": terminology,
        "uncertainties": uncertainties,
        "terminology_audit": {"violations": vio["violations"], "human_confirm": vio["human_confirm"],
                              "termbase_lock": vio.get("termbase_lock")},
        "sources": case.get("source_provenance", {}),
        "exceptions": [{"type": "missing_translation", "segment": sid} for sid in missing],
    }
    extras = {}
    for k in required:
        if k in ("case_id", "status"):
            continue
        if k in known:
            payload[k] = known[k]
        else:
            extras[k] = ("见 bilingual 与 terminology 字段；合同要求该键但本工作流无专门产物，"
                         "已给最佳努力结构化值")
            payload[k] = known["bilingual"] if k in ("segments", "paragraphs", "alignment") else \
                         known["terminology"] if k in ("terms", "terminology_table") else \
                         known["uncertainties"] if k in ("uncertainty", "open_issues", "human_confirm") else \
                         known["sources"] if k in ("evidence", "provenance") else str(known["terminology_audit"])
    if extras:
        payload["extras"] = extras

    json.dump(payload, open(os.path.join(a.out, "result.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)

    L = [f"# 双语对照（合成/实际由任务决定，case={case.get('case_id')}）", ""]
    for b in bilingual:
        tgt = b["target"] or "⟦未译⟧"
        L.append(f"## {b['id']}（{b['zone']}）")
        L.append(b["source"])
        L.append("")
        L.append(tgt)
        L.append("")
    open(os.path.join(a.out, "bilingual.md"), "w", encoding="utf-8").write("\n".join(L))
    print(f"result.json + bilingual.md -> {a.out} (status={status}, segments={len(done)}/{len(segs)}, "
          f"violations={len(vio['violations'])})")

if __name__ == "__main__":
    main()
