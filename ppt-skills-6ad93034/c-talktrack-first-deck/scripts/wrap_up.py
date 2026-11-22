#!/usr/bin/env python3
"""wrap_up.py — talktrack-first-deck step 6: final audit + result.json.

Final measured audit of the compiled deck (slide count, notes, source
lines, template part identity) merged with the narration lint, then
assembly of result.json with the seven contract root fields. content_map
carries the talk-track specifics: per-slide seconds vs budget, notes
length, anchors, figure.
"""
import json, os, re, zipfile, hashlib

IN = os.environ.get("CASE_INPUT_DIR", "/input")
WORK = os.environ.get("CASE_WORK_DIR", "/app/work")
OUT = os.environ.get("CASE_OUTPUT_DIR", "/app/output")


def jl(p, d=None):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return d


def sha_parts(path, prefs):
    out = {}
    with zipfile.ZipFile(path) as z:
        for n in z.namelist():
            if any(n.startswith(p) for p in prefs):
                out[n] = hashlib.sha256(z.read(n)).hexdigest()
    return out


def main():
    brief = jl(os.path.join(WORK, "stage_brief.json"), {}) or {}
    lint = jl(os.path.join(WORK, "track_lint.json"), {}) or {}
    derived = jl(os.path.join(WORK, "derived_map.json"), []) or []
    export = jl(os.path.join(WORK, "export_status.json"), {}) or {}
    checks, problems = {}, []

    pptx = os.path.join(OUT, "presentation.pptx")
    deck_ok = os.path.exists(pptx)
    checks["T01-talktrack-lint"] = {"status": "pass" if lint.get("pass") else "fail",
                                    "evidence": f"{len(lint.get('problems', []))} 处问题；总时长 {lint.get('total_seconds')}s"}
    if deck_ok:
        from pptx import Presentation
        prs = Presentation(pptx)
        n = len(prs.slides._sldIdLst)
        checks["T02-slide-count"] = {"status": "pass" if n == brief.get("slide_count") else "fail",
                                     "evidence": f"{n}/{brief.get('slide_count')}"}
        no_notes = no_src = 0
        for i, s in enumerate(prs.slides, 1):
            if not (s.has_notes_slide and s.notes_slide.notes_text_frame.text.strip()):
                no_notes += 1
            if not any(sh.has_text_frame and sh.text_frame.text.strip().startswith("来源")
                       for sh in s.shapes):
                no_src += 1
        checks["T03-notes"] = {"status": "pass" if no_notes == 0 else "fail",
                               "evidence": f"{no_notes} 页缺备注"}
        checks["T04-source-lines"] = {"status": "pass" if no_src == 0 else "fail",
                                      "evidence": f"{no_src} 页缺来源行"}
        base = brief.get("deck_base")
        if base and os.path.exists(base):
            pref = ("ppt/slideMasters/", "ppt/slideLayouts/", "ppt/theme/")
            a, b = sha_parts(base, pref), sha_parts(pptx, pref)
            changed = [x for x in a if x not in b or a[x] != b[x]]
            added = [x for x in b if x not in a and "notesMaster" not in x and not x.endswith("theme2.xml")]
            font_over = 0
            with zipfile.ZipFile(pptx) as z:
                for nm in z.namelist():
                    if nm.startswith("ppt/slides/slide") and nm.endswith(".xml"):
                        font_over += len(re.findall(r'typeface="', z.read(nm).decode("utf-8", "replace")))
            ok = not changed and not added and font_over == 0
            checks["T05-template-identity"] = {
                "status": "pass" if ok else "fail",
                "evidence": f"部件改动 {len(changed)}，越权新增 {len(added)}，字体覆盖 {font_over}"}
    else:
        checks["T02-slide-count"] = {"status": "fail", "evidence": "无 pptx"}
    checks["T06-export"] = {"status": "pass" if export.get("pdf") else "fail",
                            "evidence": export.get("pdf") or "; ".join(export.get("errors", []))}
    if export.get("page_check"):
        pc = export["page_check"]
        checks["T07-rendered-pages"] = {
            "status": "pass" if not pc["empty_pages"] and
            pc["pdf_pages"] == brief.get("slide_count") else "warn",
            "evidence": f"PDF {pc['pdf_pages']} 页，空白 {pc['empty_pages']}"}

    exceptions = list(brief.get("problems", [])) + list(export.get("errors", []))
    for p in lint.get("problems", []):
        if p.get("level") == "hard":
            exceptions.append(f"[{p['where']}] {p['msg']}")
    fails = [k for k, v in checks.items() if v.get("status") == "fail"]
    status = "failed" if not deck_ok else ("partial" if fails else "completed")

    result = {
        "case_id": brief.get("case_id", "UNKNOWN-CASE"),
        "status": status,
        "editable_source": {
            "path": "presentation.pptx" if deck_ok else None,
            "type": "pptx",
            "built_by": "talktrack compile（讲稿派生幻灯片）",
            "talktrack": "talktrack.md 为同源讲稿",
        },
        "export_artifact": {
            "pdf": export.get("pdf"),
            "previews_dir": "previews" if export.get("preview_pages") else None,
            "preview_pages": export.get("preview_pages", 0),
        },
        "content_map": derived,
        "compliance_checks": checks,
        "exceptions": exceptions,
        "sources": {"paper": os.path.basename(brief["paper"]) if brief.get("paper") else None,
                    "deck_base": os.path.basename(brief["deck_base"]) if brief.get("deck_base") else None},
        "uncertainty": ["讲稿时长为语速估计（中文 4.5 字/秒，英文 2.3 词/秒），实际演讲需彩排校准",
                        "图裁剪为版式启发式"],
        "time_summary": {"budget_total_s": brief.get("time_minutes", 0) * 60,
                         "planned_total_s": lint.get("total_seconds")},
    }
    with open(os.path.join(OUT, "result.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    # keep the talk track itself as a first-class deliverable
    tt = os.path.join(WORK, "talktrack.md")
    if os.path.exists(tt):
        import shutil
        shutil.copyfile(tt, os.path.join(OUT, "talktrack.md"))
    print(json.dumps({"status": status, "fails": fails}, ensure_ascii=False))


if __name__ == "__main__":
    main()
