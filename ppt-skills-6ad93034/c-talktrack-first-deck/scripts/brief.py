#!/usr/bin/env python3
"""brief.py — talktrack-first-deck step 1: stage briefing.

Reads the case, computes a per-slide TIME BUDGET (the scarce resource of a
talk), mines the paper into a digest, and freezes a terminology glossary
so slides and narration keep the paper's exact terms and symbols.

Outputs (under $WORK):
  stage_brief.json   audience/minutes/slide target/mode + assumptions
  time_budget.json   [{slide, role, seconds}] — sums to time_minutes*60
  paper_notes.md     digest (sections, figure/table list, key sentences)
  paper_text.json    [{page, text}] for anchor verification
  glossary.json      locked terms with canonical forms
  output/assets/figures/*.png  real crops (for {fig:figN} directives)
"""
import json, os, re, glob, shutil, subprocess, collections

IN = os.environ.get("CASE_INPUT_DIR", "/input")
WORK = os.environ.get("CASE_WORK_DIR", "/app/work")
OUT = os.environ.get("CASE_OUTPUT_DIR", "/app/output")

ROLE_WEIGHT = {"title": 0.5, "background": 1.0, "method": 1.3, "result": 1.4,
               "comparison": 1.1, "limitation": 0.8, "conclusion": 0.9}
SEC_WORDS = ("abstract", "introduction", "background", "related work", "method",
             "methods", "experiments", "results", "discussion", "conclusion",
             "conclusions", "limitations", "approach", "evaluation")


def jload(p):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return {}


def pages_of(pdf, problems):
    if shutil.which("pdftotext"):
        try:
            r = subprocess.run(["pdftotext", "-layout", pdf, "-"],
                               capture_output=True, timeout=120)
            ps = r.stdout.decode("utf-8", "replace").split("\f")
            if any(x.strip() for x in ps):
                return [{"page": i + 1, "text": t} for i, t in enumerate(ps) if t.strip()]
        except Exception as e:
            problems.append(f"pdftotext 失败: {e}")
    try:
        import fitz
        d = fitz.open(pdf)
        return [{"page": i + 1, "text": d[i].get_text()} for i in range(len(d))]
    except Exception as e:
        problems.append(f"文本层提取失败（疑似扫描件，需 OCR）: {e}")
        return []


def find_caps(pages):
    pats = [(re.compile(r"^(?:Figure|Fig\.?|FIGURE)\s*(\d+)[\s:：.]\s*(.*)", re.I), "figure", "fig"),
            (re.compile(r"^图\s*(\d+)[\s:：.]\s*(.*)"), "figure", "fig"),
            (re.compile(r"^(?:Table|TABLE)\s*(\d+)[\s:：.]\s*(.*)", re.I), "table", "tab"),
            (re.compile(r"^表\s*(\d+)[\s:：.]\s*(.*)"), "table", "tab")]
    caps = []
    for pg in pages:
        for rx, kind, pre in pats:
            for line in pg["text"].splitlines():
                m = rx.match(line.strip())
                if m:
                    cid = f"{pre}{m.group(1)}"
                    if not any(c["id"] == cid for c in caps):
                        caps.append({"id": cid, "kind": kind, "num": int(m.group(1)),
                                     "page": pg["page"], "caption": m.group(2).strip()[:200],
                                     "crop": None, "ok": False})
    caps.sort(key=lambda c: (c["page"], c["num"]))
    return caps


def crop(pdf, caps, problems):
    try:
        import fitz
    except Exception:
        problems.append("pymupdf 不可用，跳过图裁剪")
        return
    os.makedirs(os.path.join(OUT, "assets", "figures"), exist_ok=True)
    try:
        doc = fitz.open(pdf)
    except Exception as e:
        problems.append(f"裁剪失败: {e}")
        return
    for c in caps:
        if c["kind"] != "figure":
            continue
        try:
            page = doc[c["page"] - 1]
            rects = []
            for n in (f"Figure {c['num']}", f"Fig. {c['num']}", f"Fig {c['num']}",
                      f"图{c['num']}", f"图 {c['num']}"):
                rects = page.search_for(n)
                if rects:
                    break
            if not rects:
                continue
            cr = min(rects, key=lambda r: r.y0)
            pr = page.rect
            clip = fitz.Rect(pr.x0 + 40, max(pr.y0 + 40, cr.y0 - pr.height * 0.45),
                             pr.x1 - 40, cr.y1 + 6)
            if clip.height < 50:
                continue
            rel = os.path.join("assets", "figures", f"{c['id']}.png")
            page.get_pixmap(clip=clip, dpi=170).save(os.path.join(OUT, rel))
            c["crop"] = rel
            c["ok"] = True
        except Exception:
            pass


def build_glossary(pages, title):
    """Lock canonical term forms: acronyms, CamelCase, and title words."""
    text = "\n".join(p["text"] for p in pages)
    counts = collections.Counter()
    for tok in re.findall(r"\b[A-Za-z][A-Za-z0-9-]{2,}\b", text):
        counts[tok] += 1
    terms = []
    for tok, n in counts.most_common(400):
        if tok.isupper() and len(tok) >= 2 and n >= 2:          # acronyms: BLEU, WMT
            terms.append({"term": tok, "kind": "acronym", "count": n})
        elif re.search(r"[a-z][A-Z]", tok) and n >= 2:          # CamelCase
            terms.append({"term": tok, "kind": "camel", "count": n})
    for w in re.findall(r"[A-Za-z][A-Za-z0-9-]{3,}", title or ""):
        if not any(t["term"].lower() == w.lower() for t in terms):
            terms.append({"term": w, "kind": "title", "count": counts.get(w, 0)})
    # frequent domain nouns worth keeping verbatim
    for tok, n in counts.most_common(60):
        if n >= 8 and tok[0].isupper() and not tok.isupper() and \
           not any(t["term"] == tok for t in terms):
            terms.append({"term": tok, "kind": "frequent", "count": n})
    return terms[:80]


def allocate(n, minutes, required_roles):
    # narrative order: title -> background -> method -> result -> comparison
    # -> limitation -> conclusion; slot counts scale with narrative weight
    order = ["background", "method", "result", "comparison", "limitation", "conclusion"]
    w = {"background": 0.16, "method": 0.28, "result": 0.36, "comparison": 0.06,
         "limitation": 0.05, "conclusion": 0.09}
    counts = {r: (1 if r in required_roles else 0) for r in order}
    if not any(counts.values()):
        counts.update({"background": 1, "method": 1, "result": 1, "conclusion": 1})
    used = sum(counts.values())
    rest = max(0, (n - 1) - used)
    # largest-remainder distribution of the remaining slots
    shares = sorted(order, key=lambda r: -(w[r] * rest - int(w[r] * rest)))
    leftovers = rest - sum(int(w[r] * rest) for r in order)
    for r in order:
        counts[r] += int(w[r] * rest)
    for r in shares[:max(0, leftovers)]:
        counts[r] += 1
    roles = ["title"]
    for r in order:
        roles += [r] * counts[r]
    while len(roles) < n:
        roles.insert(-1, "result")
    roles = roles[:n]
    total = minutes * 60
    wsum = sum(ROLE_WEIGHT.get(r, 1.0) for r in roles)
    budget = []
    acc = 0
    for i, r in enumerate(roles):
        sec = round(total * ROLE_WEIGHT.get(r, 1.0) / wsum / 5) * 5
        acc += sec
        budget.append({"slide": i + 1, "role": r, "seconds": max(20, sec)})
    budget[-1]["seconds"] += total - sum(b["seconds"] for b in budget)
    return budget


def write_digest(path, title, pages, caps):
    secs = []
    for pg in pages:
        for line in pg["text"].splitlines():
            s = line.strip()
            if (s.lower() in SEC_WORDS or re.match(r"^\d+\.?\s+[A-Z][A-Za-z /-]{2,40}$", s)) \
               and s.lower() not in [x[0] for x in secs]:
                secs.append((s.lower(), s, pg["page"]))
    L = [f"# 论文摘要（讲稿撰写依据；勿读全文）\n标题: {title}\n页数: {len(pages)}\n\n## 章节"]
    L += [f"- {nm} (p{pg})" for _, nm, pg in secs]
    L.append("\n## 图表（{fig:id} 可用者标 ok）")
    for c in caps:
        L.append(f"- {c['id']} [{'ok' if c['ok'] else c['kind']}] p{c['page']}: {c['caption']}")
    L.append("\n## 各章起首句")
    for low, nm, pgno in secs:
        pg = next((p for p in pages if p["page"] == pgno), None)
        if not pg:
            continue
        idx = pg["text"].lower().find(low)
        body = re.sub(r"\s+", " ", pg["text"][idx + len(nm):] if idx >= 0 else pg["text"])
        L.append(f"\n### {nm} (p{pgno})\n" + " ".join(re.split(r"(?<=[.!?。！？])\s", body)[:2])[:600])
    open(path, "w", encoding="utf-8").write("\n".join(L))


def main():
    os.makedirs(WORK, exist_ok=True)
    os.makedirs(OUT, exist_ok=True)
    problems = []
    case = jload(os.path.join(IN, "case.json"))
    wo = jload(os.path.join(IN, "artifacts", "slide-workorder.json"))
    if not wo:
        for c in glob.glob(os.path.join(IN, "**", "*workorder*.json"), recursive=True):
            wo = jload(c)
            if wo:
                break
    material = jload(os.path.join(IN, "material.json"))
    pdfs = sorted(glob.glob(os.path.join(IN, "**", "*.pdf"), recursive=True))
    pptxs = sorted(glob.glob(os.path.join(IN, "**", "*.pptx"), recursive=True))
    starting = next((p for p in pptxs if "start" in os.path.basename(p).lower()), None)
    template = next((p for p in pptxs if p != starting), None)
    mode = str(wo.get("mode") or case.get("mode") or ("edit" if starting else "create")).lower()
    n = int(wo.get("total_slides") or wo.get("slide_count") or case.get("slide_count") or 12)
    minutes = int(wo.get("time_minutes") or case.get("time_minutes") or 15)
    if not pdfs:
        problems.append("无论文 PDF")
    if not template and not starting:
        problems.append("无模板/起始稿，将用默认空白包")
    pages, caps = [], []
    if pdfs:
        pages = pages_of(pdfs[0], problems)
        caps = find_caps(pages)
        crop(pdfs[0], caps, problems)
    budget = allocate(n, minutes, wo.get("required_roles") or
                      ["background", "method", "result", "conclusion"])
    brief = {"case_id": case.get("case_id") or wo.get("case_id") or "UNKNOWN-CASE",
             "mode": mode, "audience": wo.get("audience") or case.get("audience") or "评审专家",
             "time_minutes": minutes, "slide_count": n,
             "language": str(wo.get("language") or case.get("language") or "zh"),
             "paper": pdfs[0] if pdfs else None,
             "deck_base": (starting if mode == "edit" and starting else template),
             "figures_ok": [c["id"] for c in caps if c["ok"]],
             "problems": problems}
    json.dump(brief, open(os.path.join(WORK, "stage_brief.json"), "w"),
              ensure_ascii=False, indent=1)
    json.dump(budget, open(os.path.join(WORK, "time_budget.json"), "w"),
              ensure_ascii=False, indent=1)
    json.dump(pages, open(os.path.join(WORK, "paper_text.json"), "w"), ensure_ascii=False)
    json.dump(caps, open(os.path.join(WORK, "paper_caps.json"), "w"), ensure_ascii=False, indent=1)
    json.dump(build_glossary(pages, material.get("title", "")),
              open(os.path.join(WORK, "glossary.json"), "w"), ensure_ascii=False, indent=1)
    write_digest(os.path.join(WORK, "paper_notes.md"), material.get("title", ""), pages, caps)
    print(json.dumps({"case_id": brief["case_id"], "slides": n, "minutes": minutes,
                      "audience": brief["audience"], "budget_total_s": sum(b["seconds"] for b in budget),
                      "figures_ok": brief["figures_ok"], "problems": problems},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
