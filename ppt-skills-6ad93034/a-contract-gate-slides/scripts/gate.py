#!/usr/bin/env python3
"""gate.py — Step 5/8 of contract-gate-slides: the compliance gate.

Usage:
  python3 gate.py plan    # lint work/plan.json against requirements + paper text
  python3 gate.py deck    # audit output/presentation.pptx (+ pdf if rendered)

Writes work/gate_plan.json / work/gate_deck.json:
  {"pass": bool, "problems": [{level: hard|warn, where, msg}],
   "checks": {requirement_id: {status, evidence}}}
Hard problems must be fixed by editing the plan/deck — never by weakening
the check. Exit code is always 0; read the JSON.
"""
import json, os, re, sys, zipfile, hashlib

IN = os.environ.get("CASE_INPUT_DIR", "/input")
WORK = os.environ.get("CASE_WORK_DIR", "/app/work")
OUT = os.environ.get("CASE_OUTPUT_DIR", "/app/output")

ROLES = {"title", "background", "method", "result", "comparison",
         "limitation", "conclusion"}
NUM_RE = re.compile(r"\d+(?:,\d{3})*(?:\.\d+)?%?")
CJK_RE = re.compile(r"[一-鿿]")


def bullet_len_ok(text):
    cjk = len(CJK_RE.findall(text))
    latin = len(re.sub(CJK_RE, "", text).strip())
    return cjk <= 60 and (cjk > 0 or latin <= 90)


def norm_num(tok):
    return tok.replace(",", "").rstrip("%")


def gate_plan():
    brief = json.load(open(os.path.join(WORK, "case_brief.json"), encoding="utf-8"))
    pages = json.load(open(os.path.join(WORK, "paper_pages.json"), encoding="utf-8"))
    figs = json.load(open(os.path.join(WORK, "paper_figs.json"), encoding="utf-8"))
    problems, checks = [], {}
    try:
        plan = json.load(open(os.path.join(WORK, "plan.json"), encoding="utf-8"))
    except Exception as e:
        out = {"pass": False, "problems": [{"level": "hard", "where": "plan.json",
                                            "msg": f"plan.json 不可解析: {e}"}], "checks": {}}
        json.dump(out, open(os.path.join(WORK, "gate_plan.json"), "w"), ensure_ascii=False, indent=1)
        print(json.dumps(out["problems"], ensure_ascii=False))
        return
    slides = plan.get("slides", [])
    page_text = {p["page"]: p["text"] for p in pages}
    all_text = "\n".join(p["text"] for p in pages)
    fig_ids = {f["id"]: f for f in figs}

    if len(slides) != brief["slide_count"]:
        problems.append({"level": "hard", "where": "plan",
                         "msg": f"页数 {len(slides)} != 要求 {brief['slide_count']}"})
    checks["G02-slide-count"] = {"status": "pass" if len(slides) == brief["slide_count"] else "fail",
                                 "evidence": f"{len(slides)}/{brief['slide_count']}"}
    roles_present = {s.get("role") for s in slides}
    missing = [r for r in brief.get("required_roles", []) if r not in roles_present]
    checks["G03-roles"] = {"status": "pass" if not missing else "fail",
                           "evidence": "缺 " + ",".join(missing) if missing else "全覆盖"}
    for r in sorted(roles_present - ROLES):
        problems.append({"level": "hard", "where": "plan", "msg": f"非法角色 {r}"})

    n_bad_anchor = n_bad_num = n_dense = 0
    fig_order = []
    for s in slides:
        sn = s.get("slide")
        bullets = s.get("bullets") or []
        if s.get("role") != "title":
            if not bullets:
                problems.append({"level": "hard", "where": f"S{sn}", "msg": "无 bullet"})
            if len(bullets) > 6:
                n_dense += 1
                problems.append({"level": "hard", "where": f"S{sn}",
                                 "msg": f"{len(bullets)} 条 bullet > 6"})
        for b in bullets:
            t = b.get("text", "")
            a = b.get("anchor", "")
            if not t.strip():
                problems.append({"level": "hard", "where": f"S{sn}", "msg": "空 bullet"})
                continue
            if not bullet_len_ok(t):
                n_dense += 1
                problems.append({"level": "warn", "where": f"S{sn}", "msg": "bullet 过长"})
            m = re.match(r"^p(\d+)$", a) or re.match(r"^(fig|tab)(\d+)$", a)
            if not m:
                n_bad_anchor += 1
                problems.append({"level": "hard", "where": f"S{sn}",
                                 "msg": f"锚点格式非法: '{a}'（应为 pN / figN / tabN）"})
                continue
            if a.startswith("p"):
                pg = int(m.group(1))
                scope = page_text.get(pg)
                if scope is None:
                    n_bad_anchor += 1
                    problems.append({"level": "hard", "where": f"S{sn}",
                                     "msg": f"锚定页 p{pg} 超出论文页数"})
                    continue
            else:
                fid = a
                f = fig_ids.get(fid)
                if not f:
                    n_bad_anchor += 1
                    problems.append({"level": "hard", "where": f"S{sn}", "msg": f"图表 {fid} 不存在"})
                    continue
                scope = page_text.get(f["page"], "")
            # numeric fidelity: every number must live on the anchored page
            for tok in NUM_RE.findall(t):
                if tok in ("0",) or len(tok) >= 8:
                    continue
                if tok in scope or norm_num(tok) in scope.replace(",", ""):
                    continue
                hit = tok in all_text or norm_num(tok) in all_text.replace(",", "")
                n_bad_num += 1
                problems.append({"level": "warn" if hit else "hard", "where": f"S{sn}",
                                 "msg": f"数字 {tok} 未命中锚点 {a}" + ("（命中论文他页，改锚点）" if hit else "（论文中不存在，疑似编造）")})
        fig = s.get("figure")
        if fig:
            f = fig_ids.get(fig)
            if not f:
                problems.append({"level": "hard", "where": f"S{sn}", "msg": f"figure 引用 {fig} 不存在"})
            elif f.get("crop_status") != "ok":
                problems.append({"level": "hard", "where": f"S{sn}",
                                 "msg": f"figure {fig} 无可用裁剪（{f.get('crop_status')}），换图或置 null"})
            else:
                fig_order.append(f["num"])
        if brief.get("notes_required") and not (s.get("notes") or "").strip():
            problems.append({"level": "hard", "where": f"S{sn}", "msg": "缺少演讲备注"})
    if fig_order != sorted(fig_order):
        problems.append({"level": "warn", "where": "plan", "msg": "图序与论文出现顺序不一致"})
    checks["G06-anchor-numbers"] = {"status": "pass" if n_bad_num == 0 else "fail",
                                    "evidence": f"{n_bad_num} 处数字未命中锚点"}
    checks["G12-density"] = {"status": "pass" if n_dense == 0 else "warn",
                             "evidence": f"{n_dense} 处密度问题"}
    checks["G04-notes"] = {"status": "pass" if all((s.get("notes") or "").strip() for s in slides) else "fail",
                           "evidence": "每页备注齐全" if all((s.get("notes") or "").strip() for s in slides) else "有缺备注页"}
    checks["G07-figure-real"] = {"status": "pass", "evidence": "plan 仅允许引用已裁剪图"}
    hard = sum(1 for p in problems if p["level"] == "hard")
    out = {"pass": hard == 0, "problems": problems, "checks": checks}
    json.dump(out, open(os.path.join(WORK, "gate_plan.json"), "w"), ensure_ascii=False, indent=1)
    print(json.dumps({"pass": out["pass"], "hard": hard, "warn": len(problems) - hard},
                     ensure_ascii=False))
    for p in problems[:30]:
        print(f"[{p['level']}] {p['where']}: {p['msg']}")


def _sha(b):
    return hashlib.sha256(b).hexdigest()


def _parts(path, prefix):
    out = {}
    with zipfile.ZipFile(path) as z:
        for n in z.namelist():
            if any(n.startswith(p) for p in prefix):
                out[n] = _sha(z.read(n))
    return out


def gate_deck():
    brief = json.load(open(os.path.join(WORK, "case_brief.json"), encoding="utf-8"))
    problems, checks = [], {}
    pptx_path = os.path.join(OUT, "presentation.pptx")
    if not os.path.exists(pptx_path):
        out = {"pass": False, "problems": [{"level": "hard", "where": "deck",
                                            "msg": "presentation.pptx 不存在"}], "checks": checks}
        json.dump(out, open(os.path.join(WORK, "gate_deck.json"), "w"), ensure_ascii=False, indent=1)
        print(json.dumps(out["problems"], ensure_ascii=False))
        return
    from pptx import Presentation
    from pptx.util import Emu
    prs = Presentation(pptx_path)
    n_slides = len(prs.slides._sldIdLst)
    checks["G01-deck-editable"] = {"status": "pass", "evidence": f"python-pptx 可打开，{n_slides} 页"}
    checks["G02-slide-count"] = {"status": "pass" if n_slides == brief["slide_count"] else "fail",
                                 "evidence": f"{n_slides}/{brief['slide_count']}"}
    if n_slides != brief["slide_count"]:
        problems.append({"level": "hard", "where": "deck",
                         "msg": f"页数 {n_slides} != {brief['slide_count']}"})
    W, H = prs.slide_width, prs.slide_height
    no_notes = no_src = overflow = 0
    for i, slide in enumerate(prs.slides, 1):
        has_notes = slide.has_notes_slide and slide.notes_slide.notes_text_frame.text.strip()
        if brief.get("notes_required") and not has_notes:
            no_notes += 1
            problems.append({"level": "hard", "where": f"S{i}", "msg": "缺演讲备注"})
        texts = [sh.text_frame.text for sh in slide.shapes if sh.has_text_frame]
        if brief.get("source_line_required") and not any(
                t.strip().startswith(("来源", "Source")) for t in texts):
            no_src += 1
            problems.append({"level": "hard", "where": f"S{i}", "msg": "缺来源行"})
        for sh in slide.shapes:
            try:
                if sh.left < -Emu(9144) or sh.top < -Emu(9144) or \
                   sh.left + sh.width > W + Emu(9144) or sh.top + sh.height > H + Emu(9144):
                    overflow += 1
                    problems.append({"level": "warn", "where": f"S{i}",
                                     "msg": f"形状越界: {getattr(sh, 'name', '?')}"})
            except Exception:
                pass
    checks["G04-notes"] = {"status": "pass" if no_notes == 0 else "fail", "evidence": f"{no_notes} 页缺备注"}
    checks["G05-source-line"] = {"status": "pass" if no_src == 0 else "fail", "evidence": f"{no_src} 页缺来源行"}
    # font override scan (typeface set at run level breaks theme inheritance)
    overrides = 0
    with zipfile.ZipFile(pptx_path) as z:
        for name in z.namelist():
            if name.startswith("ppt/slides/slide") and name.endswith(".xml"):
                xml = z.read(name).decode("utf-8", "replace")
                overrides += len(re.findall(r'typeface="(?!\s*$)', xml))
    checks["G08-template-inherit"] = {"status": "pass" if overrides == 0 else "fail",
                                      "evidence": f"{overrides} 处 run 级字体名覆盖"}
    if overrides:
        problems.append({"level": "hard", "where": "deck",
                         "msg": f"{overrides} 处字体名覆盖（会破坏主题继承）"})
    tpl = brief.get("template_pptx")
    if tpl and os.path.exists(tpl):
        pref = ("ppt/slideMasters/", "ppt/slideLayouts/", "ppt/theme/")
        a, b = _parts(tpl, pref), _parts(pptx_path, pref)
        changed = [n for n in a if n not in b or a[n] != b[n]]
        added = [n for n in b if n not in a]
        # notes master + its theme are required for speaker notes; they extend
        # the package without altering the template's own master/layout/theme
        benign = [n for n in added if "notesMaster" in n or n.endswith("theme2.xml")]
        same = not changed and len(added) == len(benign)
        checks["G08-template-inherit"]["status"] = "pass" if (same and overrides == 0) else "fail"
        checks["G08-template-inherit"]["evidence"] = (
            f"模板部件 {'字节级一致' if same else '被改动: ' + ','.join(changed + [x for x in added if x not in benign])}"
            f"；新增备注母版部件 {len(benign)} 个（允许）；字体覆盖 {overrides} 处")
        if not same:
            problems.append({"level": "hard", "where": "deck",
                             "msg": "母版/版式/主题被改动: " + ",".join(changed[:5])})
    pdf = os.path.join(OUT, "presentation.pdf")
    if os.path.exists(pdf):
        try:
            import fitz
            d = fitz.open(pdf)
            ok = len(d) == n_slides
            checks["G09-export-pdf"] = {"status": "pass" if ok else "fail",
                                        "evidence": f"PDF {len(d)} 页 vs pptx {n_slides} 页"}
            if not ok:
                problems.append({"level": "hard", "where": "pdf", "msg": "PDF 页数与 pptx 不一致"})
            empty = sum(1 for i in range(len(d)) if not d[i].get_text().strip()
                        and not d[i].get_images())
            if empty:
                problems.append({"level": "warn", "where": "pdf", "msg": f"{empty} 个空白页"})
        except Exception as e:
            checks["G09-export-pdf"] = {"status": "warn", "evidence": f"PDF 检查失败: {e}"}
    else:
        checks["G09-export-pdf"] = {"status": "skip", "evidence": "无 PDF（render.py 未成功）"}
    hard = sum(1 for p in problems if p["level"] == "hard")
    out = {"pass": hard == 0, "problems": problems, "checks": checks}
    json.dump(out, open(os.path.join(WORK, "gate_deck.json"), "w"), ensure_ascii=False, indent=1)
    print(json.dumps({"pass": out["pass"], "hard": hard, "warn": len(problems) - hard},
                     ensure_ascii=False))
    for p in problems[:30]:
        print(f"[{p['level']}] {p['where']}: {p['msg']}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "deck":
        gate_deck()
    else:
        gate_plan()
