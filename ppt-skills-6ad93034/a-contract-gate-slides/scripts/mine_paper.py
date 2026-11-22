#!/usr/bin/env python3
"""mine_paper.py — Step 2 of contract-gate-slides.

Extract the paper's text layer per page, locate section headings and
figure/table captions, and crop real figure bitmaps from the PDF (never
synthesize curves). Also writes a short digest the planner should read
instead of the full paper (model budget is 64 calls / 900 s).

Outputs (under $WORK):
  paper_pages.json     [{page, text}]
  paper_sections.json  [{name, page}]
  paper_figs.json      [{id, kind, page, caption, crop, crop_status}]
  paper_digest.md      compact reading material for the planning step
Figure crops go to $OUT/assets/figures/<id>.png
"""
import json, os, re, subprocess, sys, shutil

IN = os.environ.get("CASE_INPUT_DIR", "/input")
WORK = os.environ.get("CASE_WORK_DIR", "/app/work")
OUT = os.environ.get("CASE_OUTPUT_DIR", "/app/output")

FIG_RE = re.compile(r"^(Figure|Fig\.?|FIGURE)\s*(\d+)[\s:：.]\s*(.*)", re.I)
TAB_RE = re.compile(r"^(Table|TABLE)\s*(\d+)[\s:：.]\s*(.*)", re.I)
CN_FIG_RE = re.compile(r"^图\s*(\d+)[\s:：.]\s*(.*)")
CN_TAB_RE = re.compile(r"^表\s*(\d+)[\s:：.]\s*(.*)")
SEC_RE = re.compile(r"^(\d+)\.?\s+([A-Z][A-Za-z /-]{2,40})$")
KNOWN_SECS = ("abstract", "introduction", "background", "related work", "method",
              "methods", "methodology", "experiments", "experiment", "results",
              "discussion", "conclusion", "conclusions", "limitations",
              "references", "approach", "evaluation", "setup")


def warn(warnings, msg):
    warnings.append(msg)
    print("WARN:", msg, file=sys.stderr)


def extract_pages(pdf, warnings):
    """Return [{page, text}] via pdftotext, pymupdf, or pypdf."""
    if shutil.which("pdftotext"):
        try:
            out = subprocess.run(["pdftotext", "-layout", pdf, "-"],
                                 capture_output=True, timeout=120)
            txt = out.stdout.decode("utf-8", "replace")
            pages = txt.split("\f")
            if any(p.strip() for p in pages):
                return [{"page": i + 1, "text": t} for i, t in enumerate(pages) if t.strip()]
        except Exception as e:
            warn(warnings, f"pdftotext 失败: {e}")
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(pdf)
        return [{"page": i + 1, "text": doc[i].get_text()} for i in range(len(doc))]
    except Exception as e:
        warn(warnings, f"pymupdf 不可用: {e}")
    try:
        from pypdf import PdfReader
        r = PdfReader(pdf)
        return [{"page": i + 1, "text": p.extract_text() or ""} for i, p in enumerate(r.pages)]
    except Exception as e:
        warn(warnings, f"pypdf 不可用: {e}")
    return []


def find_sections(pages):
    secs, seen = [], set()
    for pg in pages:
        for line in pg["text"].splitlines():
            s = line.strip()
            m = SEC_RE.match(s)
            cand = None
            if m:
                cand = m.group(2).strip()
            elif s.lower() in KNOWN_SECS:
                cand = s
            if cand and cand.lower() not in seen:
                seen.add(cand.lower())
                secs.append({"name": cand, "page": pg["page"]})
    return secs


def find_figs(pages):
    figs = []
    for pg in pages:
        lines = pg["text"].splitlines()
        for i, line in enumerate(lines):
            s = line.strip()
            m = FIG_RE.match(s) or CN_FIG_RE.match(s)
            kind = "figure"
            if not m:
                m = TAB_RE.match(s) or CN_TAB_RE.match(s)
                kind = "table"
            if m:
                num = m.group(2)
                cap = m.group(3).strip()
                # caption may wrap onto next line
                if len(cap) < 40 and i + 1 < len(lines):
                    nxt = lines[i + 1].strip()
                    if nxt and not (FIG_RE.match(nxt) or TAB_RE.match(nxt)):
                        cap = (cap + " " + nxt).strip()
                fid = f"{'fig' if kind == 'figure' else 'tab'}{num}"
                if not any(f["id"] == fid and f["page"] == pg["page"] for f in figs):
                    figs.append({"id": fid, "kind": kind, "num": int(num),
                                 "page": pg["page"], "caption": cap[:220],
                                 "crop": None, "crop_status": "pending"})
    figs.sort(key=lambda f: (f["page"], f["num"]))
    return figs


def crop_figures(pdf, figs, warnings):
    """Crop the bitmap region above each figure caption using PyMuPDF."""
    try:
        import fitz
    except Exception:
        warn(warnings, "无 pymupdf，跳过图片裁剪（crop_status=caption-only）")
        for f in figs:
            f["crop_status"] = "caption-only"
        return
    outdir = os.path.join(OUT, "assets", "figures")
    os.makedirs(outdir, exist_ok=True)
    try:
        doc = fitz.open(pdf)
    except Exception as e:
        warn(warnings, f"无法打开 PDF 进行裁剪: {e}")
        for f in figs:
            f["crop_status"] = "caption-only"
        return
    for f in figs:
        if f["kind"] != "figure":
            f["crop_status"] = "table-text-only"
            continue
        try:
            page = doc[f["page"] - 1]
            needles = [f"Figure {f['num']}", f"Fig. {f['num']}", f"Fig {f['num']}",
                       f"Figure{f['num']}", f"图{f['num']}", f"图 {f['num']}"]
            rects = []
            for n in needles:
                rects = page.search_for(n)
                if rects:
                    break
            if not rects:
                f["crop_status"] = "caption-not-located"
                continue
            cap_r = min(rects, key=lambda r: r.y0)  # first occurrence on page
            pr = page.rect
            # figure body heuristically occupies the area above the caption
            top = max(pr.y0 + 40, cap_r.y0 - pr.height * 0.45)
            clip = fitz.Rect(pr.x0 + 40, top, pr.x1 - 40, cap_r.y1 + 6)
            if clip.height < 50:
                f["crop_status"] = "region-too-small"
                continue
            pix = page.get_pixmap(clip=clip, dpi=170)
            path = os.path.join(outdir, f"{f['id']}.png")
            pix.save(path)
            f["crop"] = os.path.relpath(path, OUT)
            f["crop_status"] = "ok"
        except Exception as e:
            f["crop_status"] = f"error:{e}"
            warn(warnings, f"{f['id']} 裁剪失败: {e}")


def digest(pages, secs, figs, title):
    lines = [f"# 论文摘要（自动生成，供规划阅读；全文勿读）",
             f"标题: {title}", f"总页数: {len(pages)}", "", "## 章节"]
    for s in secs:
        lines.append(f"- {s['name']} (p{s['page']})")
    lines.append("\n## 图表清单")
    for f in figs:
        lines.append(f"- {f['id']} [{f['kind']}] p{f['page']}: {f['caption']}")
    lines.append("\n## 各章开头（每章前两句话）")
    for s in secs:
        pg = next((p for p in pages if p["page"] == s["page"]), None)
        if not pg:
            continue
        txt = pg["text"]
        idx = txt.lower().find(s["name"].lower())
        body = txt[idx + len(s["name"]):] if idx >= 0 else txt
        body = re.sub(r"\s+", " ", body).strip()
        sents = re.split(r"(?<=[.!?。！？])\s", body)[:2]
        lines.append(f"\n### {s['name']} (p{s['page']})")
        lines.append(" ".join(sents)[:600])
    return "\n".join(lines)


def main():
    os.makedirs(WORK, exist_ok=True)
    warnings = []
    brief = json.load(open(os.path.join(WORK, "case_brief.json"), encoding="utf-8"))
    pdf = brief.get("paper_pdf")
    if not pdf:
        for name in ("paper_pages.json", "paper_sections.json", "paper_figs.json"):
            json.dump([], open(os.path.join(WORK, name), "w"))
        open(os.path.join(WORK, "paper_digest.md"), "w").write("无论文 PDF。\n")
        print("no paper; empty index written")
        return
    pages = extract_pages(pdf, warnings)
    if not pages:
        warn(warnings, "文本层提取失败：论文可能是纯扫描件，需走 OCR 工具")
    secs = find_sections(pages)
    figs = find_figs(pages)
    if pages:
        crop_figures(pdf, figs, warnings)
    json.dump(pages, open(os.path.join(WORK, "paper_pages.json"), "w"), ensure_ascii=False)
    json.dump(secs, open(os.path.join(WORK, "paper_sections.json"), "w"), ensure_ascii=False, indent=1)
    json.dump(figs, open(os.path.join(WORK, "paper_figs.json"), "w"), ensure_ascii=False, indent=1)
    open(os.path.join(WORK, "paper_digest.md"), "w", encoding="utf-8").write(
        digest(pages, secs, figs, brief.get("material_title", "")))
    if warnings:
        json.dump(warnings, open(os.path.join(WORK, "mining_warnings.json"), "w"), ensure_ascii=False, indent=1)
    ok = sum(1 for f in figs if f["crop_status"] == "ok")
    print(json.dumps({"pages": len(pages), "sections": len(secs),
                      "figs_tables": len(figs), "crops_ok": ok,
                      "warnings": warnings}, ensure_ascii=False))


if __name__ == "__main__":
    main()
