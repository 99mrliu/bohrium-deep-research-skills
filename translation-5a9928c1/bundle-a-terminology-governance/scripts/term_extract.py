#!/usr/bin/env python3
"""term_extract.py — 确定性候选术语抽取（定义模式 + 形态 + 频次）。

用法: term_extract.py --source source.md --out candidates.json
输出: {"candidates": [{"term","abbr","kind","occurrences","first_offset",
                        "defined_by_pattern": bool}, ...]} 按优先级排序。
启发式、不claim完备；漏项由审计阶段 missing_rendering 兜住。
"""
import argparse, json, re

DEF_FULL_ABBR = re.compile(
    r'\b((?:[A-Za-z][A-Za-z-]*\s){1,4}[A-Za-z][A-Za-z-]*)\s*\(\s*([A-Z][A-Za-z-]{1,15})\s*\)')
ABBR_FULL = re.compile(
    r'\b([A-Z][A-Za-z-]{1,15})\s*\(\s*((?:[A-Za-z][A-Za-z-]*\s){1,4}[A-Za-z][A-Za-z-]*)\s*\)')
LWRD = set("the a an of and or in on at for to with by from as is are was were be been five six seven".split())
CAPS_RUN = re.compile(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,4})\b')
HYPHEN = re.compile(r'\b([a-z][a-z]+(?:-[a-z]+){1,3})\b')
STOP = set("""The This That These Those However Therefore Moreover Furthermore Figure Table Fig Eq
Section Results Conclusion Conclusions Abstract Introduction Methods Methodology References
We They Their There Here When While Because Although Since Paper Study Work Model Models Data
January February March April May June July August September October November December
University Institute Journal Science Nature Elsevier Springer Wiley arXiv""".split())

def norm(t):
    return re.sub(r'\s+', ' ', t.strip()).lower()

def count_occ(text, term):
    return len(re.findall(r'\b' + re.escape(term) + r'\b', text, flags=re.IGNORECASE))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    text = open(a.source, encoding="utf-8", errors="replace").read()

    found = {}  # norm -> record
    def tidy(full):
        toks = full.strip().split()
        # 取尾部“全小写/连字符”连续片段，再从左剥掉冠介词与数词
        run = []
        for w in reversed(toks):
            if w.islower() or '-' in w:
                run.append(w)
            else:
                break
        run.reverse()
        # 切到内部最后一个冠介词/数词之后（"conductivity of X" → X；"cations at five Ys" → Ys）
        cut = 0
        for i, w in enumerate(run[:-1]):
            if w.lower().strip(',') in LWRD or w.strip(',').isdigit():
                cut = i + 1
        run = run[cut:] or run
        while len(run) > 1 and (run[0].lower().strip(',') in LWRD or run[0].strip(',').isdigit()):
            run = run[1:]
        s = ' '.join(run) if len(run) >= 2 else ' '.join(toks)
        return s[0].lower() + s[1:] if s else s
    def add(term, abbr, kind, defined):
        if kind == "defined-term":
            term = tidy(term)
        n = norm(term)
        if not n or any(w.strip('-').lower() in ('the','a','an','of','and','in','on','for','to','with','by') for w in [term.split()[0], term.split()[-1]]):
            return
        if n in found:
            rec = found[n]
            rec["occurrences"] = count_occ(text, rec["term"])
            if abbr and not rec.get("abbr"):
                rec["abbr"] = abbr
            rec["defined_by_pattern"] = rec["defined_by_pattern"] or defined
            return
        if term in STOP or norm(term) in {s.lower() for s in STOP}:
            return
        found[n] = {"term": term.strip(), "abbr": abbr, "kind": kind,
                    "occurrences": count_occ(text, term),
                    "first_offset": text.lower().find(n),
                    "defined_by_pattern": defined}

    for m in DEF_FULL_ABBR.finditer(text):
        full, ab = m.group(1).strip(), m.group(2).strip()
        if len(full.split()) <= 6:
            add(full, ab, "defined-term", True)
            add(ab, None, "abbreviation", True)
    for m in ABBR_FULL.finditer(text):
        ab, full = m.group(1).strip(), m.group(2).strip()
        add(full, ab, "defined-term", True)
        add(ab, None, "abbreviation", True)
    for m in CAPS_RUN.finditer(text):
        add(m.group(1), None, "capitalized-multiword", False)
    for m in HYPHEN.finditer(text):
        tok = m.group(1)
        if len(tok) >= 8 and not any(c.isdigit() for c in tok):
            add(tok, None, "hyphenated-compound", False)

    cands = sorted(found.values(),
                   key=lambda r: (not r["defined_by_pattern"], -r["occurrences"], r["first_offset"]))
    for i, c in enumerate(cands):
        c["rank"] = i + 1
    json.dump({"source_chars": len(text), "candidates": cands},
              open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"{len(cands)} candidates -> {a.out}")

if __name__ == "__main__":
    main()
