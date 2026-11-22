#!/usr/bin/env python3
"""intake.py — opjournal-deck-surgeon step 1.

Snapshot the base deck as version v000 and mine the paper. The surgeon
never edits the base in place: every change is an op in the journal,
replayed onto this frozen v000.

Outputs:
  work/versions/v000_base.pptx   frozen base (template or starting deck)
  work/intake_report.json        mode, slide target, audience, assumptions
  work/paper_pages.json          [{page, text}]
  work/captions.json             [{id, kind, page, caption, crop, crop_status}]
  work/paper_brief.md            digest the surgeon reads before operating
  output/assets/figures/*.png    real crops from the paper PDF
"""
import json, os, re, shutil, subprocess, sys, glob

IN = os.environ.get("CASE_INPUT_DIR", "/input")
WORK = os.environ.get("CASE_WORK_DIR", "/app/work")
OUT = os.environ.get("CASE_OUTPUT_DIR", "/app/output")

CAP_RES = [
    (re.compile(r"^(?:Figure|Fig\.?|FIGURE)\s*(\d+)[\s:：.]\s*(.*)", re.I), "figure", "fig"),
    (re.compile(r"^图\s*(\d+)[\s:：.]\s*(.*)"), "figure", "fig"),
    (re.compile(r"^(?:Table|TABLE)\s*(\d+)[\s:：.]\s*(.*)", re.I), "table", "tab"),
    (re.compile(r"^表\s*(\d+)[\s:：.]\s*(.*)"), "table", "tab"),
]
SEC_HINTS = ("abstract", "introduction", "background", "related work", "method",
             "methods", "experiments", "results", "discussion", "conclusion",
             "conclusions", "limitations", "approach", "evaluation")


def load_json(p):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return {}


def pdf_text_pages(pdf, problems):
    if shutil.which("pdftotext"):
        try:
            r = subprocess.run(["pdftotext", "-layout", pdf, "-"],
                               capture_output=True, timeout=120)
            pages = r.stdout.decode("utf-8", "replace").split("\f")
            if any(p.strip() for p in pages):
                return [{"page": i + 1, "text": t} for i, t in enumerate(pages) if t.strip()]
        except Exception as e:
            problems.append(f"pdftotext 失败: {e}")
    try:
        import fitz
        doc = fitz.open(pdf)
        return [{"page": i + 1, "text": doc[i].get_text()} for i in range(len(doc))]
    except Exception as e:
        problems.append(f"PDF 文本层提取失败（可能为扫描件，需 OCR）: {e}")
        return []


def locate_captions(pages):
    caps = []
    for pg in pages:
        for rx, kind, prefix in CAP_RES:
            for line in pg["text"].splitlines():
                m = rx.match(line.strip())
                if m:
                    cid = f"{prefix}{m.group(1)}"
                    if not any(c["id"] == cid and c["page"] == pg["page"] for c in caps):
                        caps.append({"id": cid, "kind": kind, "num": int(m.group(1)),
                                     "page": pg["page"], "caption": m.group(2).strip()[:200],
                                     "crop": None, "crop_status": "pending"})
    caps.sort(key=lambda c: (c["page"], c["num"]))
    return caps


def crop_caps(pdf, caps, problems):
    try:
        import fitz
    except Exception:
        problems.append("无 pymupdf，图裁剪不可用")
        for c in caps:
            c["crop_status"] = "unavailable"
        return
    os.makedirs(os.path.join(OUT, "assets", "figures"), exist_ok=True)
    try:
        doc = fitz.open(pdf)
    except Exception as e:
        problems.append(f"打开 PDF 裁剪失败: {e}")
        return
    for c in caps:
        if c["kind"] != "figure":
            c["crop_status"] = "table-text-only"
            continue
        try:
            page = doc[c["page"] - 1]
            rects = []
            for needle in (f"Figure {c['num']}", f"Fig. {c['num']}", f"Fig {c['num']}",
                           f"图{c['num']}", f"图 {c['num']}"):
                rects = page.search_for(needle)
                if rects:
                    break
            if not rects:
                c["crop_status"] = "caption-not-located"
                continue
            cap_r = min(rects, key=lambda r: r.y0)
            pr = page.rect
            clip = fitz.Rect(pr.x0 + 40, max(pr.y0 + 40, cap_r.y0 - pr.height * 0.45),
                             pr.x1 - 40, cap_r.y1 + 6)
            if clip.height < 50:
                c["crop_status"] = "region-too-small"
                continue
            pix = page.get_pixmap(clip=clip, dpi=170)
            rel = os.path.join("assets", "figures", f"{c['id']}.png")
            pix.save(os.path.join(OUT, rel))
            c["crop"] = rel
            c["crop_status"] = "ok"
        except Exception as e:
            c["crop_status"] = f"error:{e}"


def write_brief(path, title, pages, caps):
    secs = []
    for pg in pages:
        for line in pg["text"].splitlines():
            s = line.strip()
            if s.lower() in SEC_HINTS or re.match(r"^\d+\.?\s+[A-Z][A-Za-z /-]{2,40}$", s):
                if s.lower() not in [x[0] for x in secs]:
                    secs.append((s.lower(), s, pg["page"]))
    L = [f"# 论文简报（供术者阅读）\n标题: {title}\n页数: {len(pages)}\n\n## 章节"]
    L += [f"- {name} (p{pg})" for _, name, pg in secs]
    L.append("\n## 图表")
    for c in caps:
        L.append(f"- {c['id']} [{c['crop_status']}] p{c['page']}: {c['caption']}")
    L.append("\n## 各章起首句")
    for low, name, pgno in secs:
        pg = next((p for p in pages if p["page"] == pgno), None)
        if not pg:
            continue
        idx = pg["text"].lower().find(low)
        body = re.sub(r"\s+", " ", (pg["text"][idx + len(name):] if idx >= 0 else pg["text"]))
        L.append(f"\n### {name} (p{pgno})\n" + " ".join(
            re.split(r"(?<=[.!?。！？])\s", body)[:2])[:600])
    open(path, "w", encoding="utf-8").write("\n".join(L))


def main():
    os.makedirs(os.path.join(WORK, "versions"), exist_ok=True)
    os.makedirs(OUT, exist_ok=True)
    problems = []
    case = load_json(os.path.join(IN, "case.json"))
    wo = load_json(os.path.join(IN, "artifacts", "slide-workorder.json"))
    if not wo:
        for cand in glob.glob(os.path.join(IN, "**", "*workorder*.json"), recursive=True):
            wo = load_json(cand)
            if wo:
                break
    material = load_json(os.path.join(IN, "material.json"))
    pdfs = sorted(glob.glob(os.path.join(IN, "**", "*.pdf"), recursive=True))
    pptxs = sorted(glob.glob(os.path.join(IN, "**", "*.pptx"), recursive=True))
    starting = next((p for p in pptxs if "start" in os.path.basename(p).lower()), None)
    template = next((p for p in pptxs if p != starting and
                     ("target" in os.path.basename(p).lower() or
                      "template" in os.path.basename(p).lower())), None) or \
        next((p for p in pptxs if p != starting), None)
    mode = str(wo.get("mode") or case.get("mode") or ("edit" if starting else "create")).lower()
    base = starting if (mode == "edit" and starting) else template
    if base is None:
        problems.append("无模板/起始稿：以 python-pptx 默认空白包为 v000")
        from pptx import Presentation
        base = os.path.join(WORK, "_blank.pptx")
        Presentation().save(base)
    shutil.copyfile(base, os.path.join(WORK, "versions", "v000_base.pptx"))

    pages, caps = [], []
    if pdfs:
        pages = pdf_text_pages(pdfs[0], problems)
        caps = locate_captions(pages)
        crop_caps(pdfs[0], caps, problems)
    else:
        problems.append("无论文 PDF：锚点核验不可用")
    json.dump(pages, open(os.path.join(WORK, "paper_pages.json"), "w"), ensure_ascii=False)
    json.dump(caps, open(os.path.join(WORK, "captions.json"), "w"), ensure_ascii=False, indent=1)
    write_brief(os.path.join(WORK, "paper_brief.md"),
                material.get("title", ""), pages, caps)
    report = {
        "case_id": case.get("case_id") or wo.get("case_id") or "UNKNOWN-CASE",
        "mode": mode,
        "base_used": os.path.basename(base),
        "slide_target": int(wo.get("total_slides") or wo.get("slide_count")
                            or case.get("slide_count") or 12),
        "audience": wo.get("audience") or case.get("audience") or "评审专家",
        "time_minutes": wo.get("time_minutes") or case.get("time_minutes") or 15,
        "base_slides": None,
        "pages": len(pages),
        "figures_ok": [c["id"] for c in caps if c["crop_status"] == "ok"],
        "problems": problems,
    }
    try:
        from pptx import Presentation
        report["base_slides"] = len(Presentation(os.path.join(WORK, "versions", "v000_base.pptx")).slides._sldIdLst)
    except Exception:
        pass
    json.dump(report, open(os.path.join(WORK, "intake_report.json"), "w"),
              ensure_ascii=False, indent=1)
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
