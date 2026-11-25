#!/usr/bin/env python3
"""align_export.py — 段号一一对应的双语对齐导出 + 合同组装。

用法: align_export.py --case /input/case.json --ledger ledger.json \
        --translations translations.json --out /app/output
产出: result.json（按 output_contract）、bilingual.md、alignment.json、coverage_report.json
状态: 全部块 done → success；部分 → partial；全缺 → failed。
"""
import argparse, hashlib, json, os

def load(p):
    return json.load(open(p, encoding="utf-8"))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True)
    ap.add_argument("--ledger", required=True)
    ap.add_argument("--translations", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    case = load(a.case)
    ledger = load(a.ledger)
    tr = load(a.translations)
    items = tr["segments"] if isinstance(tr, dict) else tr
    tmap = {it["id"]: it for it in items}
    os.makedirs(a.out, exist_ok=True)

    # 段文本从 translations 的 source 取（apply 已验证与台账一致）
    alignment, full_texts = [], []
    for b in ledger["blocks"]:
        it = tmap.get(b["id"], {})
        src = it.get("source", "")
        tgt = it.get("translation", "") or ""
        if tgt.strip():
            full_texts.append(tgt.strip())
        alignment.append({"id": b["id"], "kind": b["kind"], "page": b["page"],
                          "source": src, "target": tgt or None,
                          "anchor": f"{b['id']}@page{b['page']}"})
    done = sum(1 for al in alignment if al["target"])
    total = len(alignment)
    missing = [al["id"] for al in alignment if not al["target"]]
    status = "success" if done == total and total > 0 else ("partial" if done else "failed")

    json.dump({"alignment": alignment}, open(os.path.join(a.out, "alignment.json"), "w",
              encoding="utf-8"), ensure_ascii=False, indent=2)

    L = [f"# 双语段落对照（case={case.get('case_id')}）", "",
         f"覆盖: {done}/{total} 段；状态: {status}", ""]
    for al in alignment:
        L.append(f"## {al['id']} [{al['kind']}, page {al['page']}]")
        L.append(al["source"] or "⟦源块缺失⟧")
        L.append("")
        L.append(al["target"] or "⟦未译⟧")
        L.append("")
    open(os.path.join(a.out, "bilingual.md"), "w", encoding="utf-8").write("\n".join(L))

    contract = case.get("output_contract", {})
    required = contract.get("required", [])
    uncertainties = ([{"type": "missing_segment", "segment": sid, "detail": "段落未译"}
                      for sid in missing])
    known = {
        "translated_text": "\n\n".join(full_texts),
        "translation": "\n\n".join(full_texts),
        "bilingual": alignment,
        "bilingual_pairs": alignment,
        "alignment": alignment,
        "paragraphs": alignment,
        "terminology": tr.get("terminology", []) if isinstance(tr, dict) else [],
        "uncertainties": uncertainties,
        "coverage": {"translated": done, "total": total, "missing": missing},
        "sources": case.get("source_provenance", {}),
        "exceptions": [{"type": "missing_segment", "segment": sid} for sid in missing],
    }
    payload = {"case_id": case.get("case_id"), "status": status}
    extras = {}
    for k in required:
        if k in ("case_id", "status"):
            continue
        if k in known:
            payload[k] = known[k]
        else:
            payload[k] = known["coverage"] if k in ("completeness", "coverage_report") else \
                         known["sources"] if k in ("evidence", "provenance") else \
                         known["uncertainties"] if k in ("open_issues", "human_confirm") else \
                         known["bilingual"]
            extras[k] = "最佳努力映射，见相邻字段说明"
    if extras:
        payload["extras"] = extras
    json.dump(payload, open(os.path.join(a.out, "result.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"result.json + bilingual.md + alignment.json -> {a.out} "
          f"(status={status}, {done}/{total})")

if __name__ == "__main__":
    main()
