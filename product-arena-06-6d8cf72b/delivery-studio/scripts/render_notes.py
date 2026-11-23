#!/usr/bin/env python3
"""render_notes.py -- render authored notes JSON into a polished notes.md.

Input notes.json (agent-authored):
  {"title", "card": {field: {"value": ..., "anchor": "..."} | plain},
   "sections": [{"heading", "body", "anchors": [...]}],
   "comparison": {"columns": [...], "rows": [[...]]},     # optional
   "open_questions": [...], "limits": [...]}

Rendering rules: table of contents, section headings in the paper's own
order, anchors rendered as inline code after the sentences they ground,
comparison table when provided, open questions and limits at the end.
Standard library only.
"""
import argparse
import json


def render_value(v):
    if isinstance(v, dict):
        text = str(v.get("value", ""))
        if v.get("anchor"):
            text += " `%s`" % v["anchor"]
        return text
    return str(v)


def render(notes):
    out = ["# %s" % notes.get("title", "Paper notes"), ""]
    toc = []
    if notes.get("card"):
        toc.append("- [论文卡片](#论文卡片)")
    for sec in notes.get("sections", []):
        anchor = sec["heading"].lower().replace(" ", "-")
        toc.append("- [%s](#%s)" % (sec["heading"], anchor))
    if notes.get("comparison"):
        toc.append("- [对比表](#对比表)")
    toc.append("- [未决问题](#未决问题)")
    toc.append("- [边界与限制](#边界与限制)")
    out += ["## 目录", ""] + toc + [""]
    if notes.get("card"):
        out += ["## 论文卡片", ""]
        for field, value in notes["card"].items():
            out.append("- **%s**：%s" % (field, render_value(value)))
        out.append("")
    for sec in notes.get("sections", []):
        out += ["## %s" % sec["heading"], ""]
        body = sec.get("body", "").strip()
        if sec.get("anchors"):
            suffix = " ".join("`%s`" % a for a in sec["anchors"])
            body = body + " " + suffix
        out += [body, ""]
    if notes.get("comparison"):
        comp = notes["comparison"]
        out += ["## 对比表", "",
                "| " + " | ".join(comp["columns"]) + " |",
                "|" + "---|" * len(comp["columns"])]
        for row in comp["rows"]:
            out.append("| " + " | ".join(str(c) for c in row) + " |")
        out.append("")
    out += ["## 未决问题", ""]
    for q in notes.get("open_questions", []):
        out.append("- %s" % q)
    out += ["", "## 边界与限制", ""]
    for lim in notes.get("limits", []):
        out.append("- %s" % lim)
    out.append("")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--notes", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    with open(args.notes, encoding="utf-8") as fh:
        notes = json.load(fh)
    text = render(notes)
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(text)
    print(json.dumps({"wrote": args.out, "chars": len(text)}))


if __name__ == "__main__":
    main()
