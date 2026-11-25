#!/usr/bin/env python3
"""consistency_audit.py — 全篇术语一致性强制执行审计。

用法:
  consistency_audit.py --termbase TB --translations TR --source SRC \
      --out violations.json --report audit_report.md [--apply-lock]

违规类别:
  forbidden_variant    出现表内禁用变体（可安全回填时 --apply-lock 自动改）
  multiple_variants    同一术语出现禁用变体与锁定译名两种渲染
  missing_rendering    源文出现而译文零渲染
  count_mismatch       渲染次数 < 源出现次数（进 human_confirm，不自动改）
  untranslated_term    段译文仍含英文原词
退出码: 0=无硬性违规（允许 human_confirm 非空）；1=仍有硬性违规。
"""
import argparse, json, re, sys

ZONE_MARK = re.compile(r'<!--\s*zone:(\w[\w-]*)\s*-->')

def load(p):
    return json.load(open(p, encoding="utf-8"))

def count(text, needle):
    return len(re.findall(re.escape(needle), text, flags=re.IGNORECASE))

def zones_of(source):
    """返回 [(zone_name, start_offset)]；无显式标记时整篇为一个 body 区带。"""
    marks = [(m.start(), m.group(1).lower()) for m in ZONE_MARK.finditer(source)]
    if not marks:
        return [("body", 0)]
    zones = []
    for i, (off, name) in enumerate(marks):
        zones.append((name, off))
    return zones

def zone_at(zones, offset):
    name = zones[0][0]
    for n, off in zones:
        if offset <= off:
            break
        name = n
    return name

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--termbase", required=True)
    ap.add_argument("--translations", required=True)
    ap.add_argument("--source", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--report", required=True)
    ap.add_argument("--apply-lock", action="store_true")
    a = ap.parse_args()

    tb = load(a.termbase)
    if tb.get("lock"):
        import hashlib
        payload = json.dumps({t: (e.get("decision") or {}) for t, e in sorted(tb["terms"].items()) if e.get("decision")},
                             ensure_ascii=False, sort_keys=True).encode("utf-8")
        if hashlib.sha256(payload).hexdigest() != tb["lock"]["sha256"]:
            print("LOCK_BROKEN: refuse to audit on a tampered termbase", file=sys.stderr)
            sys.exit(2)
    source = open(a.source, encoding="utf-8", errors="replace").read()
    zones = zones_of(source)
    tr = load(a.translations)
    segs = tr["segments"] if isinstance(tr, dict) else tr

    def seg_zone(seg):
        if seg.get("zone"):
            return seg["zone"].lower()
        off = source.find(seg.get("original", "")[:60])
        return zone_at(zones, max(off, 0))

    violations, human_confirm = [], []

    if a.apply_lock:
        changed = 0
        for term, e in tb["terms"].items():
            d = e.get("decision")
            if not d or d.get("kind") != "preferred":
                continue
            for var in e.get("forbid", []):
                for seg in segs:
                    if var in seg.get("translation", ""):
                        seg["translation"] = seg["translation"].replace(var, d["target"])
                        changed += 1
        if changed:
            backup = a.translations + ".bak"
            open(backup, "w", encoding="utf-8").write(
                json.dumps(tr, ensure_ascii=False, indent=2))
            json.dump(tr, open(a.translations, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
            print(f"apply-lock: {changed} forbidden-variant occurrence(s) replaced; backup -> {backup}")

    for term, e in tb["terms"].items():
        d = e.get("decision")
        if not d:
            continue
        src_occ = count(source, term)
        if e.get("abbr"):
            src_occ += count(source, e["abbr"])
        if src_occ == 0:
            continue
        tgt = d["target"]
        per_seg = [(seg["id"], seg.get("translation", "")) for seg in segs]
        pref_occ = sum(count(t, tgt) for _, t in per_seg)
        forbidden_hits = []
        for var in e.get("forbid", []):
            for sid, t in per_seg:
                if var in t:
                    forbidden_hits.append({"variant": var, "segment": sid})
        eng_left = [(sid, term) for sid, t in per_seg
                    if re.search(re.escape(term), t, flags=re.IGNORECASE)]
        zone_pref = {}
        for seg in segs:
            z = seg_zone(seg)
            c = count(seg.get("translation", ""), tgt)
            if c:
                zone_pref[z] = zone_pref.get(z, 0) + c

        if forbidden_hits and pref_occ:
            violations.append({"term": term, "class": "multiple_variants",
                               "detail": f"locked '{tgt}' ({pref_occ}×) coexists with forbidden variant(s)",
                               "hits": forbidden_hits})
        elif forbidden_hits:
            violations.append({"term": term, "class": "forbidden_variant",
                               "detail": f"forbidden variant(s) present, locked '{tgt}' absent",
                               "hits": forbidden_hits})
        if pref_occ == 0 and d.get("kind") == "preferred" and not forbidden_hits:
            violations.append({"term": term, "class": "missing_rendering",
                               "detail": f"source has {src_occ} occurrence(s) but translation has zero '{tgt}'"})
        rendered = pref_occ + len(forbidden_hits)
        if rendered < src_occ and (pref_occ > 0 or forbidden_hits):
            human_confirm.append({"term": term, "class": "count_mismatch",
                                  "detail": f"{rendered}/{src_occ} occurrence(s) rendered; check untranslated instances",
                                  "zones": zone_pref})
        if eng_left and d.get("kind") == "preferred":
            violations.append({"term": term, "class": "untranslated_term",
                               "detail": f"English term still present in translation segments",
                               "segments": [s for s, _ in eng_left]})

    out = {"termbase_lock": (tb.get("lock") or {}).get("sha256"),
           "terms_audited": sum(1 for e in tb["terms"].values() if e.get("decision")),
           "violations": violations, "human_confirm": human_confirm,
           "apply_lock": bool(a.apply_lock)}
    json.dump(out, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    L = ["# 术语一致性审计报告", ""]
    L.append(f"- 锁定术语数: {out['terms_audited']}；硬性违规: {len(violations)}；待人工确认: {len(human_confirm)}")
    L.append("")
    for v in violations:
        L.append(f"- **{v['class']}** `{v['term']}` — {v['detail']}")
    for h in human_confirm:
        L.append(f"- 待确认 `{h['term']}` — {h['detail']}")
    if not violations and not human_confirm:
        L.append("- 全部锁定术语渲染与源出现次数一致。")
    L.append("")
    L.append("说明：审计强制执行术语口径，不证明语义正确性；count_mismatch 只提示核对，不自动改动。")
    open(a.report, "w", encoding="utf-8").write("\n".join(L) + "\n")

    print(f"violations={len(violations)} human_confirm={len(human_confirm)} -> {a.out}")
    sys.exit(1 if violations else 0)

if __name__ == "__main__":
    main()
