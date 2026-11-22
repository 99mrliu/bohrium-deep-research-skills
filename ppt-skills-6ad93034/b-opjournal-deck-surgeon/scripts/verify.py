#!/usr/bin/env python3
"""verify.py — opjournal-deck-surgeon step 4: independent post-op audit.

The journal is the surgeon's account; this script is the auditor. It opens
the replayed deck and checks the case contract WITHOUT trusting the
journal: slide count vs workorder, per-slide notes + source stamp, picture
aspect fidelity, template part byte-identity vs v000, shape bounds.

Writes work/verify.json {"pass": bool, "findings": [...], "checks": {...}}.
"""
import json, os, re, zipfile, hashlib

WORK = os.environ.get("CASE_WORK_DIR", "/app/work")
OUT = os.environ.get("CASE_OUTPUT_DIR", "/app/output")


def sha_parts(path, prefixes):
    out = {}
    with zipfile.ZipFile(path) as z:
        for n in z.namelist():
            if any(n.startswith(p) for p in prefixes):
                out[n] = hashlib.sha256(z.read(n)).hexdigest()
    return out


def main():
    findings, checks = [], []
    checks = {}
    report = json.load(open(os.path.join(WORK, "intake_report.json"), encoding="utf-8"))
    pptx_path = os.path.join(OUT, "presentation.pptx")
    if not os.path.exists(pptx_path):
        json.dump({"pass": False, "findings": [{"level": "hard", "msg": "presentation.pptx 不存在"}],
                   "checks": {}}, open(os.path.join(WORK, "verify.json"), "w"), ensure_ascii=False, indent=1)
        print("NO DECK")
        return
    from pptx import Presentation
    from pptx.util import Emu
    prs = Presentation(pptx_path)
    n_slides = len(prs.slides._sldIdLst)
    target = report["slide_target"]
    checks["slide_count"] = {"status": "pass" if n_slides == target else "fail",
                             "evidence": f"{n_slides}/{target}"}
    if n_slides != target:
        findings.append({"level": "hard", "msg": f"页数 {n_slides} != 工单 {target}"})

    no_notes = no_stamp = oob = 0
    W, H = prs.slide_width, prs.slide_height
    for i, slide in enumerate(prs.slides, 1):
        if not (slide.has_notes_slide and slide.notes_slide.notes_text_frame.text.strip()):
            no_notes += 1
            findings.append({"level": "hard", "msg": f"S{i} 缺备注"})
        txt = [sh.text_frame.text for sh in slide.shapes if sh.has_text_frame]
        if not any(t.strip().startswith("来源") for t in txt):
            no_stamp += 1
            findings.append({"level": "hard", "msg": f"S{i} 缺来源戳"})
        for sh in slide.shapes:
            try:
                if sh.left < -Emu(9144) or sh.top < -Emu(9144) or \
                   sh.left + sh.width > W + Emu(9144) or sh.top + sh.height > H + Emu(9144):
                    oob += 1
                    findings.append({"level": "warn", "msg": f"S{i} 形状越界 {getattr(sh,'name','?')}"})
            except Exception:
                pass
    checks["notes"] = {"status": "pass" if no_notes == 0 else "fail", "evidence": f"{no_notes} 页缺备注"}
    checks["source_stamp"] = {"status": "pass" if no_stamp == 0 else "fail", "evidence": f"{no_stamp} 页缺来源戳"}
    checks["bounds"] = {"status": "pass" if oob == 0 else "warn", "evidence": f"{oob} 处越界"}

    # template identity vs frozen v000
    pref = ("ppt/slideMasters/", "ppt/slideLayouts/", "ppt/theme/")
    a = sha_parts(os.path.join(WORK, "versions", "v000_base.pptx"), pref)
    b = sha_parts(pptx_path, pref)
    changed = [n for n in a if n not in b or a[n] != b[n]]
    added = [n for n in b if n not in a and "notesMaster" not in n and not n.endswith("theme2.xml")]
    font_over = 0
    with zipfile.ZipFile(pptx_path) as z:
        for n in z.namelist():
            if n.startswith("ppt/slides/slide") and n.endswith(".xml"):
                font_over += len(re.findall(r'typeface="', z.read(n).decode("utf-8", "replace")))
    ok = not changed and not added and font_over == 0
    checks["template_identity"] = {
        "status": "pass" if ok else "fail",
        "evidence": f"改动 {len(changed)} 处，越权新增 {len(added)} 处，字体覆盖 {font_over} 处"}
    if not ok:
        findings.append({"level": "hard", "msg": "模板一致性破坏: " +
                          ",".join((changed + added)[:5]) + f"；字体覆盖 {font_over}"})

    # picture aspect fidelity
    try:
        from pptx.enum.shapes import MSO_SHAPE_TYPE
        bad = 0
        for i, slide in enumerate(prs.slides, 1):
            for sh in slide.shapes:
                if sh.shape_type == MSO_SHAPE_TYPE.PICTURE:
                    import io, struct
                    blob = sh.image.blob
                    if blob[:8] == b"\x89PNG\r\n\x1a\n":
                        pw, ph = struct.unpack(">II", blob[16:24])
                        if abs((sh.width / sh.height) / (pw / ph) - 1) > 0.02:
                            bad += 1
                            findings.append({"level": "warn", "msg": f"S{i} 图片比例失真"})
        checks["figure_aspect"] = {"status": "pass" if bad == 0 else "warn",
                                   "evidence": f"{bad} 张比例失真"}
    except Exception as e:
        checks["figure_aspect"] = {"status": "skip", "evidence": str(e)}

    hard = sum(1 for f in findings if f["level"] == "hard")
    out = {"pass": hard == 0, "findings": findings, "checks": checks}
    json.dump(out, open(os.path.join(WORK, "verify.json"), "w"), ensure_ascii=False, indent=1)
    print(json.dumps({"pass": out["pass"], "hard": hard,
                      "warn": len(findings) - hard}, ensure_ascii=False))
    for f in findings[:30]:
        print(f"[{f['level']}] {f['msg']}")


if __name__ == "__main__":
    main()
