#!/usr/bin/env python3
"""verification_report.py — 渲染验证报告：每段证据 ↔ 译文 ↔ 译法依据 + 人工确认清单。"""
import argparse, json

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--translations", required=True)
    ap.add_argument("--evidence", required=True)
    ap.add_argument("--register", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    tr = json.load(open(a.translations, encoding="utf-8"))
    items = tr["segments"] if isinstance(tr, dict) else tr
    ev = json.load(open(a.evidence, encoding="utf-8"))
    reg = json.load(open(a.register, encoding="utf-8"))
    ev_by_id = {s["id"]: s for s in ev["segments"]}

    L = ["# 验证报告（逐段证据 ↔ 译文 ↔ 译法依据）", "",
         f"状态: {reg['status']}；段 {reg['n_translated']}/{reg['n_segments']}；"
         f"未决不确定性 {reg['n_uncertainties']} 项", ""]
    for it in items:
        e = ev_by_id.get(it.get("id"), {})
        L.append(f"## {it.get('id')} — verdict: {e.get('verdict', 'n/a')}")
        L.append(f"- 证据: offset {e.get('resolved_start')} "
                 f"(declared {e.get('declared_start')}), "
                 f"quote_sha256 {str(e.get('quote_sha256'))[:12]}…")
        L.append(f"- 引文: “{(it.get('evidence') or {}).get('quote', '')[:200]}”")
        L.append(f"- 译法依据 ({(it.get('evidence') or {}).get('basis', 'n/a')}): "
                 f"{(it.get('evidence') or {}).get('note', '')}")
        L.append(f"- 译文: {it.get('translation', '')[:300]}")
        if it.get("uncertainty"):
            L.append(f"- ⚠ 不确定性: {it['uncertainty'].get('type')} — {it['uncertainty'].get('detail')}")
        L.append("")
    L.append("## 人工确认清单")
    if not reg["register"]:
        L.append("- 无。")
    for r in reg["register"]:
        L.append(f"- [{r.get('type')}] segment={r.get('segment')} — {r.get('detail')}")
    L.append("")
    L.append("说明：机器核验证明引文与源文本一致及覆盖无缺口；不评价译文语言质量。")
    open(a.out, "w", encoding="utf-8").write("\n".join(L) + "\n")
    print(f"verification report -> {a.out}")

if __name__ == "__main__":
    main()
