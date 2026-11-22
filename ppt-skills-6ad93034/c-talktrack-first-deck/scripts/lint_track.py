#!/usr/bin/env python3
"""lint_track.py — talktrack-first-deck step 3: narration linter.

Validates work/talktrack.md BEFORE any slide exists — the talk track is
the primary artifact; slides are derived from it later.

talktrack.md format (machine-readable):
  [S1 | 45s | 封面标题]
  讲稿正文（对本页受众说的话，1-4 句）……
  - 要点一 (anchor p1)
  - 要点二 (anchor fig1)
  {fig:fig1}            <- 可选，插图指令，只能取 brief 打印的 figures_ok

Checks: slide markers complete & ordered; per-slide seconds match the
budget (±25%); total within ±10%; notes length plausible for the seconds
(CJK ≈ 4.5 chars/s, Latin ≈ 2.3 words/s, 0.4x–2.5x tolerated); bullets
≤6 with anchors; every number hits its anchor page; glossary terms keep
canonical casing; figure directives reference real crops.

Writes work/track_lint.json; prints problems. Exit always 0.
"""
import json, os, re, sys

WORK = os.environ.get("CASE_WORK_DIR", "/app/work")
HDR_RE = re.compile(r"^\[S(\d+)\s*\|\s*(\d+)s\s*\|\s*(.+?)\s*\]\s*$")
FIG_RE = re.compile(r"^\{fig:(fig\d+)\}\s*$")
NUM_RE = re.compile(r"\d+(?:,\d{3})*(?:\.\d+)?%?")
CJK_RE = re.compile(r"[一-鿿]")
ANCHOR_RE = re.compile(r"\(anchor\s+(p\d+|fig\d+|tab\d+)\)")


def speech_units(text):
    cjk = len(CJK_RE.findall(text))
    words = len(re.sub(CJK_RE, " ", text).split())
    return cjk / 4.5 + words / 2.3   # estimated seconds


def parse(path):
    slides, cur = [], None
    for raw in open(path, encoding="utf-8"):
        line = raw.rstrip("\n")
        m = HDR_RE.match(line.strip())
        if m:
            if cur:
                slides.append(cur)
            cur = {"slide": int(m.group(1)), "seconds": int(m.group(2)),
                   "title": m.group(3), "paras": [], "bullets": [], "fig": None}
            continue
        if cur is None:
            continue
        s = line.strip()
        if not s:
            continue
        fm = FIG_RE.match(s)
        if fm:
            cur["fig"] = fm.group(1)
        elif s.startswith("- "):
            cur["bullets"].append(s[2:])
        else:
            cur["paras"].append(s)
    if cur:
        slides.append(cur)
    return slides


def main():
    problems = []
    brief = json.load(open(os.path.join(WORK, "stage_brief.json"), encoding="utf-8"))
    budget = {b["slide"]: b for b in json.load(open(os.path.join(WORK, "time_budget.json"), encoding="utf-8"))}
    pages = {p["page"]: p["text"] for p in json.load(open(os.path.join(WORK, "paper_text.json"), encoding="utf-8"))}
    caps = {c["id"]: c for c in json.load(open(os.path.join(WORK, "paper_caps.json"), encoding="utf-8"))}
    glossary = json.load(open(os.path.join(WORK, "glossary.json"), encoding="utf-8"))
    path = os.path.join(WORK, "talktrack.md")
    if not os.path.exists(path):
        print("work/talktrack.md 不存在；请先撰写讲稿")
        json.dump({"pass": False, "problems": [{"level": "hard", "where": "talktrack",
                                                "msg": "talktrack.md 缺失"}]},
                  open(os.path.join(WORK, "track_lint.json"), "w"), ensure_ascii=False, indent=1)
        return
    slides = parse(path)
    n_target = brief["slide_count"]
    nums = [s["slide"] for s in slides]
    if nums != list(range(1, len(slides) + 1)):
        problems.append({"level": "hard", "where": "talktrack", "msg": "页标号不连续/乱序"})
    if len(slides) != n_target:
        problems.append({"level": "hard", "where": "talktrack",
                         "msg": f"讲稿页数 {len(slides)} != 工单 {n_target}"})
    total_s = sum(s["seconds"] for s in slides)
    target_s = brief["time_minutes"] * 60
    if abs(total_s - target_s) > 0.10 * target_s:
        problems.append({"level": "hard", "where": "talktrack",
                         "msg": f"总时长 {total_s}s 与预算 {target_s}s 偏差 >10%"})
    all_text = "\n".join(pages.values()).replace(",", "")
    for s in slides:
        sn = s["slide"]
        b = budget.get(sn)
        if b and abs(s["seconds"] - b["seconds"]) > 0.25 * max(b["seconds"], 1):
            problems.append({"level": "warn", "where": f"S{sn}",
                             "msg": f"页时长 {s['seconds']}s 偏离预算 {b['seconds']}s"})
        notes = " ".join(s["paras"])
        if not notes.strip():
            problems.append({"level": "hard", "where": f"S{sn}", "msg": "讲稿正文为空"})
        est = speech_units(notes)
        if notes.strip() and not (0.4 * s["seconds"] <= est <= 2.5 * s["seconds"]):
            problems.append({"level": "warn", "where": f"S{sn}",
                             "msg": f"讲稿估计 {int(est)}s 与标称 {s['seconds']}s 不符"})
        if len(s["bullets"]) > 6:
            problems.append({"level": "hard", "where": f"S{sn}", "msg": "要点 >6 条"})
        for bl in s["bullets"]:
            am = ANCHOR_RE.search(bl)
            if not am:
                problems.append({"level": "hard", "where": f"S{sn}",
                                 "msg": f"要点缺 (anchor …): {bl[:30]}"})
                continue
            a = am.group(1)
            if a.startswith("p"):
                scope = pages.get(int(a[1:]))
                if scope is None:
                    problems.append({"level": "hard", "where": f"S{sn}", "msg": f"锚定页 {a} 不存在"})
                    continue
            else:
                c = caps.get(a)
                if not c:
                    problems.append({"level": "hard", "where": f"S{sn}", "msg": f"图表 {a} 不存在"})
                    continue
                scope = pages.get(c["page"], "")
            flat = scope.replace(",", "")
            for tok in NUM_RE.findall(re.sub(ANCHOR_RE, "", bl)):
                if tok == "0" or len(tok) >= 8:
                    continue
                if tok in scope or tok.rstrip("%") in flat:
                    continue
                where = "论文他页" if (tok in all_text or tok.rstrip("%") in all_text) else "论文中不存在"
                lvl = "warn" if where == "论文他页" else "hard"
                problems.append({"level": lvl, "where": f"S{sn}",
                                 "msg": f"数字 {tok} 未命中 {a}（{where}）"})
        # narration numbers must at least exist somewhere in the paper
        for tok in NUM_RE.findall(notes):
            if tok == "0" or len(tok) >= 8:
                continue
            if tok in all_text or tok.rstrip("%") in all_text:
                continue
            problems.append({"level": "hard", "where": f"S{sn}",
                             "msg": f"讲稿数字 {tok} 在论文中不存在（疑似编造）"})
        if s["fig"]:
            c = caps.get(s["fig"])
            if not c or not c.get("ok"):
                problems.append({"level": "hard", "where": f"S{sn}",
                                 "msg": f"{{fig:{s['fig']}}} 无可用裁剪"})
        # terminology lock: canonical casing for glossary terms
        body = (s["title"] + " " + notes + " " + " ".join(s["bullets"]))
        for t in glossary:
            term = t["term"]
            if t["kind"] in ("acronym", "camel", "title", "frequent") and len(term) >= 3:
                for m in re.finditer(re.escape(term), body, re.I):
                    if m.group(0) != term:
                        problems.append({"level": "warn", "where": f"S{sn}",
                                         "msg": f"术语写法 '{m.group(0)}' 应为 '{term}'"})
    hard = sum(1 for p in problems if p["level"] == "hard")
    out = {"pass": hard == 0, "problems": problems,
           "slides": len(slides), "total_seconds": total_s}
    json.dump(out, open(os.path.join(WORK, "track_lint.json"), "w"), ensure_ascii=False, indent=1)
    print(json.dumps({"pass": out["pass"], "hard": hard,
                      "warn": len(problems) - hard, "total_seconds": total_s},
                     ensure_ascii=False))
    for p in problems[:40]:
        print(f"[{p['level']}] {p['where']}: {p['msg']}")


if __name__ == "__main__":
    main()
