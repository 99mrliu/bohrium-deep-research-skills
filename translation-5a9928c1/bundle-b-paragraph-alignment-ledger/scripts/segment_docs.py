#!/usr/bin/env python3
"""segment_docs.py — 语义分段 + 跨栏伪影修复（留痕）。

子命令:
  run            --input /input --out segments.json
  repair-report  --segments segments.json --out repair_report.md

块类型: heading | paragraph | caption | formula | listitem | pagebreak 不计块。
修复（仅两类，逐条记录，不静默）:
  * 行尾硬连字符断词 "bounda-\nry"  → "boundary"
  * 段内单换行                      → 合并为一个空格
"""
import argparse, hashlib, json, os, re, shutil, subprocess, sys

def sha(t):
    return hashlib.sha256(t.encode("utf-8")).hexdigest()

CAPTION = re.compile(r'^(Figure|Fig\.?|Table)\s*\d+', re.IGNORECASE)
HEADING = re.compile(r'^(?:\d+(\.\d+)*\s+)?(Abstract|Introduction|Methods?|Results?|Discussion|Conclusion|Conclusions|References?|Acknowledg|Appendix)\s*$')
FORMULA = re.compile(r'^\s*(\$\$.*\$\$|\\\(|\\\[[\s\S]*?\\\]|\(?\d+\)?$)')

def read_source(input_dir):
    for name in sorted(os.listdir(input_dir)):
        p = os.path.join(input_dir, name)
        if not os.path.isfile(p):
            continue
        if name.lower().endswith((".txt", ".md")):
            return open(p, encoding="utf-8", errors="replace").read(), name, "text"
        if name.lower().endswith(".pdf"):
            out = p + ".extract.txt"
            try:
                r = subprocess.run(["pdftotext", "-enc", "UTF-8", p, out],
                                   capture_output=True, timeout=120)
                if r.returncode == 0 and os.path.exists(out):
                    return open(out, encoding="utf-8", errors="replace").read(), name, "pdf"
            except FileNotFoundError:
                pass
            return "", name, "pdf-unreadable"
    return "", None, "none"

def repair_linebreaks(text):
    """返回 (修复后文本, repairs[])。只处理跨栏断词与段内单换行。"""
    repairs = []
    # 1) 行尾连字符断词
    def dehyphen(m):
        whole = m.group(1) + m.group(2)
        repairs.append({"type": "dehyphen", "from": m.group(0).replace("\n", "\\n"),
                        "to": whole})
        return whole
    text = re.sub(r'([A-Za-z]{2,})-\n([a-z]{2,})', dehyphen, text)
    # 2) 段内单换行 → 空格（保留空行分段、保留题注/公式行边界）
    lines = text.split("\n")
    out = []
    for i, ln in enumerate(lines):
        if (ln.strip() and out and out[-1].strip()
                and not CAPTION.match(ln.strip()) and not FORMULA.match(ln.strip())
                and not HEADING.match(ln.strip()) and i > 0
                and lines[i-1].strip() and not lines[i-1].strip().endswith(('.', ';', ':', '?', '!'))
                and not CAPTION.match(lines[i-1].strip()) and not FORMULA.match(lines[i-1].strip())
                and not HEADING.match(lines[i-1].strip())):
            prev = out.pop()
            joined = prev + " " + ln.strip()
            repairs.append({"type": "join-line", "from": prev[-40:] + "\\n" + ln.strip()[:40],
                            "to": joined[-80:]})
            out.append(joined)
        else:
            out.append(ln)
    return "\n".join(out), repairs

def segment(text, repairs):
    """按 \f 分页、空行分段；题注/公式/标题/列表项独立成块。"""
    blocks = []
    page = 1
    chunks = text.split("\f")
    for pg, chunk in enumerate(chunks, start=1):
        page = pg
        paras = re.split(r'\n\s*\n', chunk)
        for para in paras:
            p = para.strip()
            if not p:
                continue
            lines = [l.strip() for l in p.split("\n") if l.strip()]
            if len(lines) == 1 and HEADING.match(lines[0]):
                kind = "heading"
            elif all(CAPTION.match(l) for l in lines):
                kind = "caption"
            elif all(FORMULA.match(l) for l in lines):
                kind = "formula"
            elif all(re.match(r'^[-*•]\s+|^\d+[.)]\s+', l) for l in lines):
                kind = "listitem"
            else:
                kind = "paragraph"
            blocks.append({"kind": kind, "text": p, "page": page})
    return blocks

def cmd_run(a):
    text, name, how = read_source(a.input)
    if how in ("none", "pdf-unreadable") or len(text.strip()) < 20:
        json.dump({"source": name, "blocks": [], "error": how},
                  open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"ERROR: unreadable source ({how})", file=sys.stderr)
        sys.exit(2)
    repaired, repairs = repair_linebreaks(text)
    blocks = segment(repaired, repairs)
    segs = []
    for i, b in enumerate(blocks, start=1):
        segs.append({"id": f"p{i:03d}", "kind": b["kind"], "page": b["page"],
                     "text": b["text"], "sha256": sha(b["text"])})
    json.dump({"source": name, "source_how": how, "repairs": repairs, "segments": segs},
              open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"{len(segs)} segments ({len(repairs)} repairs) -> {a.out}")

def cmd_report(a):
    d = json.load(open(a.segments, encoding="utf-8"))
    L = ["# 跨栏修复报告（不静默改动的留痕）", ""]
    if not d.get("repairs"):
        L.append("未发现跨栏断词或段内单换行伪影。")
    for r in d["repairs"]:
        L.append(f"- `{r['type']}`: `{r['from']}` → `{r['to']}`")
    L.append("")
    L.append("说明：仅修复排版伪影；语义分段边界不因排版改变而合并。")
    open(a.out, "w", encoding="utf-8").write("\n".join(L) + "\n")
    print(f"repair report -> {a.out} ({len(d.get('repairs', []))} repairs)")

def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("run"); p.add_argument("--input", required=True); p.add_argument("--out", required=True); p.set_defaults(fn=cmd_run)
    p = sp.add_parser("repair-report"); p.add_argument("--segments", required=True); p.add_argument("--out", required=True); p.set_defaults(fn=cmd_report)
    a = ap.parse_args(); a.fn(a)

if __name__ == "__main__":
    main()
